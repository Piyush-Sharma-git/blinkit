"""
routes/admin.py - the INTERNAL company dashboard (Sales Department).

Every route except login is protected by @staff_required(...):
    @staff_required()            any active employee (Sales Executive and above)
    @staff_required("manager")   Sales Manager or Administrator
    @staff_required("admin")     Administrator only
"""
import sqlite3
from datetime import date, datetime, timedelta

from flask import (Blueprint, abort, flash, g, redirect, render_template, request, session,
                   url_for)

from auth import hash_password, login_employee, safe_next, staff_required, verify_password
from db import execute, get_db, query_all, query_one
from forms import (CustomerDetailsForm, EmployeeForm, LoginForm, OrderForm, PaymentStatusForm,
                   ProductForm, StatusForm)
from services import (OrderError, change_order_status, change_payment_status, create_order,
                      delete_order, parse_items)

admin_bp = Blueprint("admin", __name__)

# Revenue only counts orders that were not cancelled.
NOT_CANCELLED = "status != 'cancelled'"

ORDER_SORTS = {
    "date_desc": "order_date DESC, order_id DESC",
    "date_asc": "order_date ASC, order_id ASC",
    "total_desc": "total_amount DESC",
    "total_asc": "total_amount ASC",
}
CUSTOMER_SORTS = {
    "name": "c.full_name ASC",
    "spent": "total_spent DESC",
    "orders": "order_count DESC",
    "recent": "last_order DESC",
}
PRODUCT_SORTS = {
    "name": "p.name ASC, p.brand ASC",
    "stock": "p.stock_qty ASC",
    "price": "p.price DESC",
    "sold": "units_sold DESC",
}


# =================================================================== login
@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if g.employee:
        return redirect(url_for("admin.dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        emp = query_one("SELECT employee_id, password_hash, role, is_active FROM employees "
                        "WHERE email = ?", (form.email.data.strip().lower(),))
        if emp and emp["is_active"] and verify_password(emp["password_hash"], form.password.data):
            login_employee(emp)
            flash("Welcome back.", "success")
            return redirect(safe_next(url_for("admin.dashboard")))
        flash("Invalid email or password, or the account is inactive.", "error")
    return render_template("admin/login.html", form=form)


@admin_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("admin.login"))


# =============================================================== dashboard
@admin_bp.route("/")
@staff_required()
def dashboard():
    today = date.today().isoformat()
    month_start = date.today().replace(day=1).isoformat()

    kpi = query_one(f"""
        SELECT COUNT(*)                         AS orders,
               COALESCE(SUM(total_amount), 0)   AS revenue,
               COALESCE(AVG(total_amount), 0)   AS avg_order,
               COALESCE(SUM(CASE WHEN date(order_date) = ? THEN total_amount END), 0) AS today_revenue,
               COUNT(CASE WHEN date(order_date) = ? THEN 1 END)                       AS today_orders,
               COALESCE(SUM(CASE WHEN date(order_date) >= ? THEN total_amount END), 0) AS month_revenue
        FROM orders WHERE {NOT_CANCELLED}""", (today, today, month_start))
    customers = query_one("SELECT COUNT(*) AS n FROM customers")["n"]
    low_stock_count = query_one("SELECT COUNT(*) AS n FROM products "
                                "WHERE is_active = 1 AND stock_qty <= min_stock")["n"]
    my_month = query_one(f"""SELECT COUNT(*) AS orders, COALESCE(SUM(total_amount), 0) AS revenue
                             FROM orders WHERE employee_id = ? AND {NOT_CANCELLED}
                             AND date(order_date) >= ?""",
                         (g.employee["employee_id"], month_start))

    by_category = query_all(f"""
        SELECT c.name AS category, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
        FROM order_items oi
        JOIN orders o     ON o.order_id = oi.order_id AND o.{NOT_CANCELLED}
        JOIN products p   ON p.product_id = oi.product_id
        JOIN categories c ON c.category_id = p.category_id
        GROUP BY c.category_id ORDER BY revenue DESC""")

    # Daily revenue for the last 30 days (days with no sales filled with 0 in Python).
    start = date.today() - timedelta(days=29)
    daily_rows = query_all(f"""SELECT date(order_date) AS day, ROUND(SUM(total_amount), 2) AS revenue
                               FROM orders WHERE {NOT_CANCELLED} AND date(order_date) >= ?
                               GROUP BY day""", (start.isoformat(),))
    daily_map = {r["day"]: r["revenue"] for r in daily_rows}
    days = [(start + timedelta(days=i)).isoformat() for i in range(30)]
    daily = {"labels": [d[5:] for d in days], "series": [daily_map.get(d, 0) for d in days]}

    recent = query_all("SELECT * FROM order_summary ORDER BY order_date DESC, order_id DESC LIMIT 8")
    low_stock = query_all("""SELECT p.product_id, p.name, p.brand, p.stock_qty, p.min_stock,
                                    c.name AS category
                             FROM products p JOIN categories c ON c.category_id = p.category_id
                             WHERE p.is_active = 1 AND p.stock_qty <= p.min_stock
                             ORDER BY p.stock_qty ASC LIMIT 8""")
    return render_template("admin/dashboard.html", kpi=kpi, customers=customers,
                           low_stock_count=low_stock_count, my_month=my_month,
                           by_category={"labels": [r["category"] for r in by_category],
                                        "series": [r["revenue"] for r in by_category]},
                           daily=daily, recent=recent, low_stock=low_stock)


# ================================================================== orders
@admin_bp.route("/orders")
@staff_required()
def orders():
    f = {k: request.args.get(k, "").strip() for k in
         ("q", "status", "payment_status", "channel", "date_from", "date_to", "sort")}
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = 25

    where, params = ["1 = 1"], []
    if f["q"]:
        digits = f["q"].upper().replace("BLK-", "")
        if digits.isdigit():                      # search by transaction ID
            where.append("order_id = ?")
            params.append(int(digits))
        else:                                     # or by customer name
            where.append("customer_name LIKE ?")
            params.append(f"%{f['q']}%")
    for col in ("status", "payment_status", "channel"):
        if f[col]:
            where.append(f"{col} = ?")            # column name is fixed by us, value is bound
            params.append(f[col])
    if f["date_from"]:
        where.append("date(order_date) >= ?")
        params.append(f["date_from"])
    if f["date_to"]:
        where.append("date(order_date) <= ?")
        params.append(f["date_to"])
    where_sql = " AND ".join(where)
    order_by = ORDER_SORTS.get(f["sort"], ORDER_SORTS["date_desc"])

    summary = query_one(f"""SELECT COUNT(*) AS n, COALESCE(SUM(CASE WHEN status != 'cancelled'
                                 THEN total_amount END), 0) AS revenue
                            FROM order_summary WHERE {where_sql}""", params)
    rows = query_all(f"""SELECT * FROM order_summary WHERE {where_sql}
                         ORDER BY {order_by} LIMIT ? OFFSET ?""",
                     params + [per_page, (page - 1) * per_page])
    pages = max((summary["n"] + per_page - 1) // per_page, 1)
    return render_template("admin/orders.html", orders=rows, f=f, page=page, pages=pages,
                           summary=summary)


def _order_form_choices(form):
    customers = query_all("SELECT customer_id, full_name, phone FROM customers ORDER BY full_name")
    form.customer_id.choices = [(0, "-- Select customer --")] + [
        (c["customer_id"], f"{c['full_name']} ({c['phone']})") for c in customers]
    return query_all("""SELECT p.product_id, p.name, p.brand, p.price, p.stock_qty,
                               c.name AS category
                        FROM products p JOIN categories c ON c.category_id = p.category_id
                        WHERE p.is_active = 1 ORDER BY c.name, p.name, p.brand""")


@admin_bp.route("/orders/new", methods=["GET", "POST"])
@staff_required()
def order_new():
    form = OrderForm()
    products = _order_form_choices(form)
    rows = [("", "1")]                                    # one empty product row to start

    if request.method == "GET" and request.args.get("customer_id", type=int):
        form.customer_id.data = request.args.get("customer_id", type=int)

    if request.method == "POST":
        product_ids = request.form.getlist("product_id")
        quantities = request.form.getlist("quantity")
        rows = list(zip(product_ids, quantities)) or rows   # re-show what was typed
        if form.validate_on_submit():
            if form.customer_id.data == 0:
                form.customer_id.errors.append("Choose a customer.")
            else:
                try:
                    items = parse_items(product_ids, quantities)
                    order_date = f"{form.order_date.data.isoformat()} {datetime.now():%H:%M:%S}"
                    order_id = create_order(
                        get_db(), customer_id=form.customer_id.data, items=items,
                        payment_method=form.payment_method.data,
                        payment_status=form.payment_status.data, channel="staff",
                        employee_id=g.employee["employee_id"], order_date=order_date,
                        notes=form.notes.data)
                except OrderError as err:
                    flash(str(err), "error")
                else:
                    flash(f"Transaction BLK-{order_id:06d} saved.", "success")
                    # Post/Redirect/Get: refreshing the next page cannot resubmit the form.
                    return redirect(url_for("admin.order_detail", order_id=order_id))
    return render_template("admin/order_form.html", form=form, products=products, rows=rows)


@admin_bp.route("/orders/<int:order_id>")
@staff_required()
def order_detail(order_id):
    order = query_one("SELECT * FROM order_summary WHERE order_id = ?", (order_id,))
    if order is None:
        abort(404)
    extra = query_one("SELECT notes, created_at FROM orders WHERE order_id = ?", (order_id,))
    payment = query_one("SELECT * FROM payments WHERE order_id = ?", (order_id,))
    items = query_all("""SELECT oi.product_id, oi.quantity, oi.unit_price, p.name, p.brand,
                                c.name AS category, ROUND(oi.quantity * oi.unit_price, 2) AS line_total
                         FROM order_items oi
                         JOIN products p   ON p.product_id = oi.product_id
                         JOIN categories c ON c.category_id = p.category_id
                         WHERE oi.order_id = ? ORDER BY p.name""", (order_id,))
    status_form = StatusForm(status=order["status"])
    payment_form = PaymentStatusForm(payment_status=order["payment_status"])
    return render_template("admin/order_detail.html", order=order, extra=extra, payment=payment,
                           items=items, status_form=status_form, payment_form=payment_form)


@admin_bp.route("/orders/<int:order_id>/status", methods=["POST"])
@staff_required()
def order_status(order_id):
    form = StatusForm()
    if form.validate_on_submit():
        try:
            change_order_status(get_db(), order_id, form.status.data)
            flash("Order status updated.", "success")
        except OrderError as err:
            flash(str(err), "error")
    return redirect(url_for("admin.order_detail", order_id=order_id))


@admin_bp.route("/orders/<int:order_id>/payment", methods=["POST"])
@staff_required()
def order_payment(order_id):
    form = PaymentStatusForm()
    if form.validate_on_submit():
        try:
            change_payment_status(get_db(), order_id, form.payment_status.data)
            flash("Payment status updated.", "success")
        except OrderError as err:
            flash(str(err), "error")
    return redirect(url_for("admin.order_detail", order_id=order_id))


@admin_bp.route("/orders/<int:order_id>/delete", methods=["POST"])
@staff_required("manager")
def order_delete(order_id):
    try:
        delete_order(get_db(), order_id)
        flash(f"Transaction BLK-{order_id:06d} deleted and stock restored.", "success")
    except OrderError as err:
        flash(str(err), "error")
        return redirect(url_for("admin.order_detail", order_id=order_id))
    return redirect(url_for("admin.orders"))


# =============================================================== customers
@admin_bp.route("/customers")
@staff_required()
def customers():
    q = request.args.get("q", "").strip()
    sort = request.args.get("sort", "name")
    sql = f"""SELECT c.customer_id, c.full_name, c.email, c.phone, c.city, c.is_sample,
                     COUNT(o.order_id)                 AS order_count,
                     COALESCE(SUM(o.total_amount), 0)  AS total_spent,
                     MAX(o.order_date)                 AS last_order
              FROM customers c
              LEFT JOIN orders o ON o.customer_id = c.customer_id AND o.{NOT_CANCELLED}"""
    params = []
    if q:
        sql += " WHERE c.full_name LIKE ? OR c.email LIKE ? OR c.phone LIKE ? OR c.city LIKE ?"
        params = [f"%{q}%"] * 4
    sql += f" GROUP BY c.customer_id ORDER BY {CUSTOMER_SORTS.get(sort, CUSTOMER_SORTS['name'])}"
    return render_template("admin/customers.html", customers=query_all(sql, params), q=q, sort=sort)


def _customer_unique_errors(form, exclude_id=None):
    """Return True if email/phone already belong to ANOTHER customer."""
    clash = False
    email = form.email.data.strip().lower()
    if query_one("SELECT 1 FROM customers WHERE email = ? AND customer_id != ?",
                 (email, exclude_id or 0)):
        form.email.errors.append("Another customer already uses this email.")
        clash = True
    if query_one("SELECT 1 FROM customers WHERE phone = ? AND customer_id != ?",
                 (form.phone.data, exclude_id or 0)):
        form.phone.errors.append("Another customer already uses this mobile number.")
        clash = True
    return clash


@admin_bp.route("/customers/new", methods=["GET", "POST"])
@staff_required()
def customer_new():
    form = CustomerDetailsForm()
    if form.validate_on_submit() and not _customer_unique_errors(form):
        cur = execute("""INSERT INTO customers (full_name, email, phone, address, city)
                         VALUES (?, ?, ?, ?, ?)""",
                      (form.full_name.data.strip(), form.email.data.strip().lower(),
                       form.phone.data, form.address.data.strip(), form.city.data.strip()))
        flash("Customer created.", "success")
        if request.args.get("then") == "order":           # came from the order form
            return redirect(url_for("admin.order_new", customer_id=cur.lastrowid))
        return redirect(url_for("admin.customer_detail", customer_id=cur.lastrowid))
    return render_template("admin/customer_form.html", form=form, customer=None)


@admin_bp.route("/customers/<int:customer_id>")
@staff_required()
def customer_detail(customer_id):
    customer = query_one("SELECT * FROM customers WHERE customer_id = ?", (customer_id,))
    if customer is None:
        abort(404)
    stats = query_one(f"""SELECT COUNT(*) AS orders, COALESCE(SUM(total_amount), 0) AS spent,
                                 COALESCE(AVG(total_amount), 0) AS avg_order,
                                 MAX(order_date) AS last_order
                          FROM orders WHERE customer_id = ? AND {NOT_CANCELLED}""", (customer_id,))
    fav = query_one(f"""SELECT c.name, SUM(oi.quantity) AS units
                        FROM order_items oi
                        JOIN orders o     ON o.order_id = oi.order_id AND o.{NOT_CANCELLED}
                        JOIN products p   ON p.product_id = oi.product_id
                        JOIN categories c ON c.category_id = p.category_id
                        WHERE o.customer_id = ?
                        GROUP BY c.category_id ORDER BY units DESC LIMIT 1""", (customer_id,))
    orders = query_all("SELECT * FROM order_summary WHERE customer_id = ? ORDER BY order_date DESC",
                       (customer_id,))
    return render_template("admin/customer_detail.html", customer=customer, stats=stats,
                           fav=fav, orders=orders)


@admin_bp.route("/customers/<int:customer_id>/edit", methods=["GET", "POST"])
@staff_required()
def customer_edit(customer_id):
    customer = query_one("SELECT * FROM customers WHERE customer_id = ?", (customer_id,))
    if customer is None:
        abort(404)
    form = CustomerDetailsForm(data=dict(customer) if request.method == "GET" else None)
    if form.validate_on_submit() and not _customer_unique_errors(form, customer_id):
        execute("""UPDATE customers SET full_name = ?, email = ?, phone = ?, address = ?, city = ?
                   WHERE customer_id = ?""",
                (form.full_name.data.strip(), form.email.data.strip().lower(), form.phone.data,
                 form.address.data.strip(), form.city.data.strip(), customer_id))
        flash("Customer updated.", "success")
        return redirect(url_for("admin.customer_detail", customer_id=customer_id))
    return render_template("admin/customer_form.html", form=form, customer=customer)


@admin_bp.route("/customers/<int:customer_id>/delete", methods=["POST"])
@staff_required("manager")
def customer_delete(customer_id):
    try:
        cur = execute("DELETE FROM customers WHERE customer_id = ?", (customer_id,))
    except sqlite3.IntegrityError:
        # FOREIGN KEY ... ON DELETE RESTRICT: customers with orders cannot be deleted.
        get_db().rollback()
        flash("This customer has orders, so they cannot be deleted (sales history must be kept).",
              "error")
        return redirect(url_for("admin.customer_detail", customer_id=customer_id))
    if cur.rowcount == 0:
        abort(404)
    flash("Customer deleted.", "success")
    return redirect(url_for("admin.customers"))


# ================================================================ products
@admin_bp.route("/products")
@staff_required()
def products():
    q = request.args.get("q", "").strip()
    category_id = request.args.get("category", type=int)
    stock = request.args.get("stock", "")
    sort = request.args.get("sort", "name")
    sql = f"""SELECT p.*, c.name AS category,
                     COALESCE((SELECT SUM(oi.quantity) FROM order_items oi
                               JOIN orders o ON o.order_id = oi.order_id AND o.{NOT_CANCELLED}
                               WHERE oi.product_id = p.product_id), 0) AS units_sold
              FROM products p JOIN categories c ON c.category_id = p.category_id WHERE 1 = 1"""
    params = []
    if q:
        sql += " AND (p.name LIKE ? OR p.brand LIKE ? OR CAST(p.product_id AS TEXT) = ?)"
        params += [f"%{q}%", f"%{q}%", q]
    if category_id:
        sql += " AND p.category_id = ?"
        params.append(category_id)
    if stock == "low":
        sql += " AND p.stock_qty <= p.min_stock"
    elif stock == "out":
        sql += " AND p.stock_qty = 0"
    sql += f" ORDER BY {PRODUCT_SORTS.get(sort, PRODUCT_SORTS['name'])}"
    categories = query_all("SELECT category_id, name FROM categories ORDER BY name")
    return render_template("admin/products.html", products=query_all(sql, params),
                           categories=categories, q=q, category_id=category_id,
                           stock=stock, sort=sort)


def _product_form(product=None):
    form = ProductForm(data=dict(product) if product and request.method == "GET" else None)
    form.category_id.choices = [(c["category_id"], c["name"]) for c in
                                query_all("SELECT category_id, name FROM categories ORDER BY name")]
    return form


def _save_product(form, product_id=None):
    values = (form.name.data.strip(), form.brand.data.strip(), form.category_id.data,
              float(form.price.data), float(form.mrp.data), form.stock_qty.data,
              form.min_stock.data, form.max_stock.data, 1 if form.is_active.data else 0)
    try:
        if product_id is None:
            cur = execute("""INSERT INTO products (name, brand, category_id, price, mrp, stock_qty,
                                                   min_stock, max_stock, is_active)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", values)
            return cur.lastrowid
        execute("""UPDATE products SET name = ?, brand = ?, category_id = ?, price = ?, mrp = ?,
                          stock_qty = ?, min_stock = ?, max_stock = ?, is_active = ?
                   WHERE product_id = ?""", values + (product_id,))
        return product_id
    except sqlite3.IntegrityError:
        get_db().rollback()
        form.name.errors.append("A product with this name and brand already exists.")
        return None


@admin_bp.route("/products/new", methods=["GET", "POST"])
@staff_required("manager")
def product_new():
    form = _product_form()
    if form.validate_on_submit():
        pid = _save_product(form)
        if pid:
            flash("Product added.", "success")
            return redirect(url_for("admin.products", q=pid))
    return render_template("admin/product_form.html", form=form, product=None)


@admin_bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@staff_required("manager")
def product_edit(product_id):
    product = query_one("SELECT * FROM products WHERE product_id = ?", (product_id,))
    if product is None:
        abort(404)
    form = _product_form(product)
    if form.validate_on_submit():
        if _save_product(form, product_id):
            # Old orders keep their own unit_price, so changing the price here
            # does not rewrite sales history.
            flash("Product updated.", "success")
            return redirect(url_for("admin.products", q=product_id))
    return render_template("admin/product_form.html", form=form, product=product)


# ================================================================= reports
@admin_bp.route("/reports")
@staff_required("manager")
def reports():
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    cond, params = [f"o.{NOT_CANCELLED}"], []
    if date_from:
        cond.append("date(o.order_date) >= ?")
        params.append(date_from)
    if date_to:
        cond.append("date(o.order_date) <= ?")
        params.append(date_to)
    w = " AND ".join(cond)

    totals = query_one(f"""SELECT COUNT(*) AS orders, COALESCE(SUM(total_amount), 0) AS revenue,
                                  COALESCE(AVG(total_amount), 0) AS avg_order,
                                  COUNT(DISTINCT customer_id) AS customers
                           FROM orders o WHERE {w}""", params)

    monthly = query_all(f"""SELECT strftime('%Y-%m', o.order_date) AS month, COUNT(*) AS orders,
                                   ROUND(SUM(o.total_amount), 2) AS revenue
                            FROM orders o WHERE {w} GROUP BY month ORDER BY month""", params)

    by_category = query_all(f"""
        SELECT c.name AS category, SUM(oi.quantity) AS units, COUNT(DISTINCT o.order_id) AS orders,
               ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue,
               ROUND(SUM(oi.quantity * oi.unit_price) * c.standard_margin_pct / 100.0, 2) AS est_margin
        FROM order_items oi
        JOIN orders o     ON o.order_id = oi.order_id
        JOIN products p   ON p.product_id = oi.product_id
        JOIN categories c ON c.category_id = p.category_id
        WHERE {w} GROUP BY c.category_id ORDER BY revenue DESC""", params)

    top_products = query_all(f"""
        SELECT p.product_id, p.name, p.brand, c.name AS category, SUM(oi.quantity) AS units,
               ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
        FROM order_items oi
        JOIN orders o     ON o.order_id = oi.order_id
        JOIN products p   ON p.product_id = oi.product_id
        JOIN categories c ON c.category_id = p.category_id
        WHERE {w} GROUP BY p.product_id ORDER BY revenue DESC LIMIT 10""", params)

    by_employee = query_all(f"""
        SELECT COALESCE(e.full_name, 'Website (online orders)') AS seller, e.role,
               COUNT(*) AS orders, ROUND(SUM(o.total_amount), 2) AS revenue,
               ROUND(AVG(o.total_amount), 2) AS avg_order
        FROM orders o LEFT JOIN employees e ON e.employee_id = o.employee_id
        WHERE {w} GROUP BY o.employee_id ORDER BY revenue DESC""", params)

    by_payment = query_all(f"""
        SELECT p.method, COUNT(*) AS orders, ROUND(SUM(o.total_amount), 2) AS revenue
        FROM orders o JOIN payments p ON p.order_id = o.order_id
        WHERE {w} GROUP BY p.method ORDER BY revenue DESC""", params)

    # HAVING filters groups AFTER aggregation: customers with 3+ orders.
    repeat_customers = query_all(f"""
        SELECT c.customer_id, c.full_name, c.city, COUNT(*) AS orders,
               ROUND(SUM(o.total_amount), 2) AS spent
        FROM orders o JOIN customers c ON c.customer_id = o.customer_id
        WHERE {w} GROUP BY c.customer_id HAVING COUNT(*) >= 3
        ORDER BY spent DESC LIMIT 10""", params)

    # Subquery: orders worth more than the average order.
    above_avg = query_one(f"""
        SELECT COUNT(*) AS n, ROUND((SELECT AVG(total_amount) FROM orders o WHERE {w}), 2) AS avg
        FROM orders o WHERE {w}
          AND o.total_amount > (SELECT AVG(total_amount) FROM orders o WHERE {w})""",
                          params * 3)

    # NOT EXISTS subquery: active products with no sales in the period.
    never_sold = query_all(f"""
        SELECT p.product_id, p.name, p.brand, c.name AS category, p.stock_qty
        FROM products p JOIN categories c ON c.category_id = p.category_id
        WHERE p.is_active = 1 AND NOT EXISTS (
            SELECT 1 FROM order_items oi JOIN orders o ON o.order_id = oi.order_id
            WHERE oi.product_id = p.product_id AND {w})
        ORDER BY c.name, p.name""", params)

    return render_template("admin/reports.html", totals=totals, monthly=monthly,
                           by_category=by_category, top_products=top_products,
                           by_employee=by_employee, by_payment=by_payment,
                           repeat_customers=repeat_customers, above_avg=above_avg,
                           never_sold=never_sold, date_from=date_from, date_to=date_to,
                           chart={"labels": [m["month"] for m in monthly],
                                  "series": [m["revenue"] for m in monthly]})


# =============================================================== employees
@admin_bp.route("/employees", methods=["GET", "POST"])
@staff_required("admin")
def employees():
    form = EmployeeForm()
    if form.validate_on_submit():
        try:
            execute("""INSERT INTO employees (full_name, email, password_hash, role)
                       VALUES (?, ?, ?, ?)""",
                    (form.full_name.data.strip(), form.email.data.strip().lower(),
                     hash_password(form.password.data), form.role.data))
        except sqlite3.IntegrityError:
            get_db().rollback()
            form.email.errors.append("An employee with this email already exists.")
        else:
            flash("Employee account created.", "success")
            return redirect(url_for("admin.employees"))
    staff = query_all(f"""SELECT e.*, COUNT(o.order_id) AS orders,
                                 COALESCE(SUM(o.total_amount), 0) AS revenue
                          FROM employees e
                          LEFT JOIN orders o ON o.employee_id = e.employee_id AND o.{NOT_CANCELLED}
                          GROUP BY e.employee_id ORDER BY e.role DESC, e.full_name""")
    return render_template("admin/employees.html", form=form, staff=staff)


@admin_bp.route("/employees/<int:employee_id>/toggle", methods=["POST"])
@staff_required("admin")
def employee_toggle(employee_id):
    if employee_id == g.employee["employee_id"]:
        flash("You cannot deactivate your own account.", "error")
    else:
        cur = execute("UPDATE employees SET is_active = 1 - is_active WHERE employee_id = ?",
                      (employee_id,))
        if cur.rowcount == 0:
            abort(404)
        flash("Employee status changed.", "success")
    return redirect(url_for("admin.employees"))


# ================================================================= profile
@admin_bp.route("/profile")
@staff_required()
def profile():
    me = query_one("SELECT * FROM employees WHERE employee_id = ?", (g.employee["employee_id"],))
    stats = query_one(f"""SELECT COUNT(*) AS orders, COALESCE(SUM(total_amount), 0) AS revenue,
                                 COALESCE(AVG(total_amount), 0) AS avg_order
                          FROM orders WHERE employee_id = ? AND {NOT_CANCELLED}""",
                      (me["employee_id"],))
    recent = query_all("""SELECT * FROM order_summary WHERE employee_id = ?
                          ORDER BY order_date DESC LIMIT 10""", (me["employee_id"],))
    return render_template("admin/profile.html", me=me, stats=stats, recent=recent)
