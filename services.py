"""
services.py - the business rules for sales transactions.

Both the customer checkout and the staff "New order" form call
create_order(), so the rules live in ONE place:

  * prices always come from the database, never from the browser
  * the total is calculated here, in Python
  * the order, its items, the payment and the stock change are saved in
    ONE database transaction: either everything is saved, or nothing is
"""
import sqlite3
from datetime import datetime

PAYMENT_METHODS = {"upi": "UPI", "card": "Card", "cash": "Cash", "cod": "Cash on delivery"}
ORDER_STATUSES = ["placed", "delivered", "cancelled"]
PAYMENT_STATUSES = ["pending", "paid", "failed", "refunded"]

# Which status changes are allowed. Delivered and cancelled are final.
ALLOWED_STATUS_CHANGES = {"placed": {"delivered", "cancelled"}, "delivered": set(), "cancelled": set()}

MAX_QTY_PER_LINE = 1000


class OrderError(Exception):
    """A business-rule problem we can show to the user as a friendly message."""


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_items(product_ids, quantities):
    """
    Turn two parallel form lists into {product_id: quantity}.
    Blank rows are skipped, the same product entered twice is merged (so the
    order never has duplicate lines), and bad numbers raise OrderError.
    """
    items = {}
    for raw_pid, raw_qty in zip(product_ids, quantities):
        raw_pid, raw_qty = (raw_pid or "").strip(), (raw_qty or "").strip()
        if not raw_pid and not raw_qty:
            continue                                  # empty row
        if not raw_pid:
            raise OrderError("Choose a product for every row that has a quantity.")
        try:
            pid, qty = int(raw_pid), int(raw_qty)
        except ValueError:
            raise OrderError("Quantity must be a whole number.")
        if qty < 1 or qty > MAX_QTY_PER_LINE:
            raise OrderError(f"Quantity must be between 1 and {MAX_QTY_PER_LINE}.")
        items[pid] = items.get(pid, 0) + qty
    for qty in items.values():
        if qty > MAX_QTY_PER_LINE:
            raise OrderError(f"Total quantity of one product cannot exceed {MAX_QTY_PER_LINE}.")
    return items


def create_order(db, *, customer_id, items, payment_method, payment_status,
                 channel, employee_id=None, order_date=None, notes=None):
    """
    Save a complete order. Returns the new order_id (the transaction ID).

    items: dict {product_id: quantity}
    Raises OrderError with a readable message if anything is wrong; in that
    case NOTHING is written to the database.
    """
    if not items:
        raise OrderError("Add at least one product to the order.")
    if payment_method not in PAYMENT_METHODS:
        raise OrderError("Choose a valid payment method.")
    if payment_status not in ("pending", "paid", "failed"):
        raise OrderError("Choose a valid payment status.")
    order_date = order_date or now_str()

    try:
        # `with db:` starts a transaction. If the block finishes, it COMMITs.
        # If any exception is raised inside it, it ROLLs BACK every change.
        with db:
            if db.execute("SELECT 1 FROM customers WHERE customer_id = ?",
                          (customer_id,)).fetchone() is None:
                raise OrderError("Customer not found.")

            # Fetch the real prices. The f-string only inserts "?,?,?" -
            # the actual IDs are still passed as bound parameters.
            placeholders = ",".join("?" * len(items))
            rows = db.execute(
                f"SELECT product_id, name, brand, price, stock_qty, is_active "
                f"FROM products WHERE product_id IN ({placeholders})",
                tuple(items)).fetchall()
            products = {r["product_id"]: r for r in rows}

            total = 0.0
            for pid, qty in items.items():
                p = products.get(pid)
                if p is None or not p["is_active"]:
                    raise OrderError(f"Product {pid} is not available.")
                total += p["price"] * qty
            total = round(total, 2)

            cur = db.execute(
                "INSERT INTO orders (customer_id, employee_id, channel, order_date, "
                "total_amount, notes) VALUES (?, ?, ?, ?, ?, ?)",
                (customer_id, employee_id, channel, order_date, total, notes or None))
            order_id = cur.lastrowid               # generated transaction ID

            for pid, qty in items.items():
                p = products[pid]
                db.execute(
                    "INSERT INTO order_items (order_id, product_id, quantity, unit_price) "
                    "VALUES (?, ?, ?, ?)", (order_id, pid, qty, p["price"]))
                # Reduce stock ONLY if enough is left. Doing the check inside the
                # UPDATE makes it safe even if two orders arrive at once.
                upd = db.execute(
                    "UPDATE products SET stock_qty = stock_qty - ? "
                    "WHERE product_id = ? AND stock_qty >= ?", (qty, pid, qty))
                if upd.rowcount != 1:
                    raise OrderError(f"Not enough stock for {p['name']} ({p['brand']}): "
                                     f"only {p['stock_qty']} left.")

            db.execute(
                "INSERT INTO payments (order_id, method, status, amount, paid_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (order_id, payment_method, payment_status, total,
                 order_date if payment_status == "paid" else None))
    except sqlite3.IntegrityError as exc:
        # A constraint (CHECK, FOREIGN KEY, UNIQUE...) rejected the data.
        raise OrderError("The order breaks a database rule and was not saved.") from exc

    return order_id


def _restore_stock(db, order_id):
    db.execute(
        "UPDATE products SET stock_qty = stock_qty + "
        "(SELECT quantity FROM order_items oi WHERE oi.order_id = ? AND oi.product_id = products.product_id) "
        "WHERE product_id IN (SELECT product_id FROM order_items WHERE order_id = ?)",
        (order_id, order_id))


def change_order_status(db, order_id, new_status):
    """placed -> delivered | cancelled. Cancelling puts the stock back and refunds."""
    order = db.execute("SELECT status FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    if order is None:
        raise OrderError("Order not found.")
    if new_status == order["status"]:
        return
    if new_status not in ALLOWED_STATUS_CHANGES[order["status"]]:
        raise OrderError(f"A {order['status']} order cannot be changed to {new_status}.")
    with db:
        db.execute("UPDATE orders SET status = ? WHERE order_id = ?", (new_status, order_id))
        if new_status == "cancelled":
            _restore_stock(db, order_id)
            db.execute("UPDATE payments SET status = 'refunded' "
                       "WHERE order_id = ? AND status = 'paid'", (order_id,))


def change_payment_status(db, order_id, new_status):
    row = db.execute(
        "SELECT o.status AS order_status, p.status AS pay_status "
        "FROM orders o JOIN payments p ON p.order_id = o.order_id WHERE o.order_id = ?",
        (order_id,)).fetchone()
    if row is None:
        raise OrderError("Order not found.")
    if new_status not in PAYMENT_STATUSES:
        raise OrderError("Invalid payment status.")
    if new_status == "paid" and row["order_status"] == "cancelled":
        raise OrderError("A cancelled order cannot be marked as paid.")
    if new_status == "refunded" and row["pay_status"] != "paid":
        raise OrderError("Only a paid order can be refunded.")
    with db:
        db.execute("UPDATE payments SET status = ?, "
                   "paid_at = CASE WHEN ? = 'paid' THEN ? ELSE paid_at END "
                   "WHERE order_id = ?", (new_status, new_status, now_str(), order_id))


def delete_order(db, order_id):
    """Managers only. Puts stock back (unless already cancelled), then deletes.
    order_items and payments are removed by ON DELETE CASCADE."""
    order = db.execute("SELECT status FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    if order is None:
        raise OrderError("Order not found.")
    with db:
        if order["status"] != "cancelled":
            _restore_stock(db, order_id)
        db.execute("DELETE FROM orders WHERE order_id = ?", (order_id,))
