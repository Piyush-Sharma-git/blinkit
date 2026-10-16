"""
routes/public.py - the CUSTOMER interface (public website).

Every function below follows the same pattern:
    URL  ->  Python function  ->  SQL query  ->  render_template(...)

Rules for this file: only public data (products, categories) is shown to
visitors, and a logged-in customer only ever sees rows WHERE customer_id
equals their own ID.
"""
import sqlite3

from flask import (Blueprint, abort, flash, g, redirect, render_template, request, session,
                   url_for)

from auth import customer_required, hash_password, login_customer, safe_next, verify_password
from db import execute, get_db, query_all, query_one
from forms import CheckoutForm, LoginForm, RegisterForm
from services import OrderError, create_order

public_bp = Blueprint("public", __name__)

# The Excel file has 268 rows but only 51 product NAMES: "Cheese" is sold by
# 5 different brands, "Pet Treats" by 12, and so on. The shop therefore shows
# ONE card per product name. GROUP BY collapses all brands of a name into one
# row; COUNT / MIN / SUM summarise them. Each card opens /item/<name>, which
# lists every brand. (The staff Products page still lists all 268 rows.)
CATALOG_SELECT = """
    SELECT p.name,
           c.name                AS category,
           c.category_id,
           COUNT(*)              AS brand_count,      -- how many brands sell it
           MIN(p.price)          AS min_price,        -- cheapest brand
           MAX(p.price)          AS max_price,
           SUM(p.stock_qty)      AS total_stock,      -- stock across all brands
           MAX(CAST(ROUND((p.mrp - p.price) * 100.0 / p.mrp) AS INTEGER)) AS max_discount,
           (SELECT p2.product_id FROM products p2      -- subquery: cheapest brand in stock
             WHERE p2.name = p.name AND p2.is_active = 1 AND p2.stock_qty > 0
             ORDER BY p2.price LIMIT 1)                AS cheapest_id
    FROM products p
    JOIN categories c ON c.category_id = p.category_id
    WHERE p.is_active = 1"""
CATALOG_GROUP = " GROUP BY p.name, c.category_id"

# Whitelist for ?sort=... Column names cannot be passed as ? parameters, so
# we map the user's choice to fixed SQL text instead of inserting it directly.
PRODUCT_SORTS = {
    "name": "p.name ASC",
    "price_asc": "min_price ASC",
    "price_desc": "min_price DESC",
    "discount": "max_discount DESC, p.name ASC",
}


# ------------------------------------------------------------------ pages
@public_bp.route("/")
def home():
    categories = query_all("""
        SELECT c.category_id, c.name, COUNT(DISTINCT p.name) AS product_count
        FROM categories c
        LEFT JOIN products p ON p.category_id = c.category_id AND p.is_active = 1
        GROUP BY c.category_id
        ORDER BY c.name""")
    # Best sellers. A CTE ("WITH ... AS") names two sub-results and joins them:
    #   catalog = one row per product name, sales = units sold per product name.
    popular = query_all(f"""
        WITH catalog AS ({CATALOG_SELECT}{CATALOG_GROUP}),
             sales AS (
                SELECT p.name, SUM(oi.quantity) AS units
                FROM order_items oi
                JOIN orders o   ON o.order_id = oi.order_id AND o.status != 'cancelled'
                JOIN products p ON p.product_id = oi.product_id
                GROUP BY p.name)
        SELECT catalog.*, sales.units
        FROM catalog JOIN sales ON sales.name = catalog.name
        ORDER BY sales.units DESC
        LIMIT 8""")
    total_items = query_one("SELECT COUNT(*) AS n FROM products WHERE is_active = 1")["n"]
    return render_template("public/home.html", categories=categories, popular=popular,
                           total_items=total_items)


@public_bp.route("/about")
def about():
    return render_template("public/about.html")


@public_bp.route("/contact")
def contact():
    return render_template("public/contact.html")


@public_bp.route("/products")
def products():
    q = request.args.get("q", "").strip()
    category_id = request.args.get("category", type=int)
    sort = request.args.get("sort", "name")
    order_by = PRODUCT_SORTS.get(sort, PRODUCT_SORTS["name"])

    sql, params = CATALOG_SELECT, []
    if q:                                   # WHERE filters rows BEFORE grouping
        sql += " AND (p.name LIKE ? OR p.brand LIKE ? OR c.name LIKE ?)"
        like = f"%{q}%"
        params += [like, like, like]
    if category_id:
        sql += " AND p.category_id = ?"
        params.append(category_id)
    sql += CATALOG_GROUP
    sql += f" ORDER BY {order_by}"          # safe: order_by comes from the whitelist

    rows = query_all(sql, params)
    categories = query_all("SELECT category_id, name FROM categories ORDER BY name")
    return render_template("public/products.html", products=rows, categories=categories,
                           q=q, category_id=category_id, sort=sort)


@public_bp.route("/item/<name>")
def item(name):
    """All brands of one product name, e.g. /item/Cheese -> 5 brands."""
    variants = query_all("""
        SELECT p.product_id, p.name, p.brand, p.price, p.mrp, p.stock_qty, p.min_stock,
               c.name AS category, c.category_id, c.shelf_life_days
        FROM products p JOIN categories c ON c.category_id = p.category_id
        WHERE p.name = ? AND p.is_active = 1
        ORDER BY p.price ASC""", (name,))
    if not variants:
        abort(404)
    more = query_all(CATALOG_SELECT + " AND p.category_id = ? AND p.name != ?" + CATALOG_GROUP +
                     " ORDER BY RANDOM() LIMIT 4", (variants[0]["category_id"], name))
    return render_template("public/item.html", name=name, variants=variants,
                           first=variants[0], more=more)


@public_bp.route("/products/<int:product_id>")
def product_detail(product_id):
    product = query_one("""
        SELECT p.*, c.name AS category, c.shelf_life_days
        FROM products p JOIN categories c ON c.category_id = p.category_id
        WHERE p.product_id = ? AND p.is_active = 1""", (product_id,))
    if product is None:
        abort(404)
    # Other brands of the same product, cheapest first.
    related = query_all("""
        SELECT p.product_id, p.name, p.brand, p.price, p.mrp, p.stock_qty, c.name AS category
        FROM products p JOIN categories c ON c.category_id = p.category_id
        WHERE p.name = ? AND p.product_id != ? AND p.is_active = 1
        ORDER BY p.price LIMIT 4""", (product["name"], product_id))
    return render_template("public/product_detail.html", product=product, related=related)


# ------------------------------------------------------------------- cart
# The cart lives in the session cookie as {"product_id": quantity}.
# It holds IDs and quantities only - prices are always re-read from the DB.

def _cart():
    return session.setdefault("cart", {})


@public_bp.route("/cart/add", methods=["POST"])
def cart_add():
    product_id = request.form.get("product_id", type=int)
    qty = request.form.get("quantity", default=1, type=int)
    product = query_one("SELECT product_id, name, stock_qty FROM products "
                        "WHERE product_id = ? AND is_active = 1", (product_id,))
    if product is None or qty is None or qty < 1:
        flash("That product could not be added.", "error")
        return redirect(request.referrer or url_for("public.products"))

    cart = _cart()
    new_qty = cart.get(str(product_id), 0) + qty
    if new_qty > product["stock_qty"]:
        flash(f"Sorry, only {product['stock_qty']} of {product['name']} in stock.", "error")
    else:
        cart[str(product_id)] = new_qty
        session.modified = True              # tell Flask the dict inside changed
        flash(f"Added {product['name']} to your cart.", "success")
    return redirect(request.referrer or url_for("public.products"))


@public_bp.route("/cart/update", methods=["POST"])
def cart_update():
    product_id = request.form.get("product_id", type=int)
    qty = request.form.get("quantity", default=0, type=int)
    cart = _cart()
    key = str(product_id)
    if key in cart:
        if qty is None or qty <= 0:
            cart.pop(key)
        else:
            stock = query_one("SELECT stock_qty FROM products WHERE product_id = ?", (product_id,))
            cart[key] = min(qty, stock["stock_qty"]) if stock else 0
            if cart[key] <= 0:
                cart.pop(key)
        session.modified = True
    return redirect(url_for("public.cart"))


def _cart_lines():
    """Join the session cart with current DB prices. Returns (lines, total)."""
    cart = _cart()
    if not cart:
        return [], 0.0
    ids = [int(k) for k in cart]
    placeholders = ",".join("?" * len(ids))
    rows = query_all(f"""SELECT p.product_id, p.name, p.brand, p.price, p.mrp, p.stock_qty,
                                c.name AS category
                         FROM products p JOIN categories c ON c.category_id = p.category_id
                         WHERE p.product_id IN ({placeholders}) AND p.is_active = 1""", ids)
    lines, total = [], 0.0
    for r in rows:
        qty = cart[str(r["product_id"])]
        line_total = round(r["price"] * qty, 2)
        total += line_total
        lines.append({"p": r, "qty": qty, "line_total": line_total})
    return lines, round(total, 2)


@public_bp.route("/cart")
def cart():
    lines, total = _cart_lines()
    return render_template("public/cart.html", lines=lines, total=total)


@public_bp.route("/checkout", methods=["GET", "POST"])
@customer_required
def checkout():
    lines, total = _cart_lines()
    if not lines:
        flash("Your cart is empty.", "warning")
        return redirect(url_for("public.products"))

    form = CheckoutForm()
    if form.validate_on_submit():
        items = {line["p"]["product_id"]: line["qty"] for line in lines}
        # Simulated payment: UPI/card succeed instantly, cash on delivery stays pending.
        pay_status = "pending" if form.payment_method.data == "cod" else "paid"
        try:
            order_id = create_order(get_db(), customer_id=g.customer["customer_id"],
                                    items=items, payment_method=form.payment_method.data,
                                    payment_status=pay_status, channel="online",
                                    notes=form.notes.data)
        except OrderError as err:
            flash(str(err), "error")
        else:
            session.pop("cart", None)
            flash("Order placed! This is a simulated checkout - no money was charged.", "success")
            return redirect(url_for("public.my_order_detail", order_id=order_id))
    return render_template("public/checkout.html", lines=lines, total=total, form=form)


# ---------------------------------------------------------------- account
@public_bp.route("/account/orders")
@customer_required
def my_orders():
    orders = query_all("""SELECT * FROM order_summary WHERE customer_id = ?
                          ORDER BY order_date DESC""", (g.customer["customer_id"],))
    return render_template("public/my_orders.html", orders=orders)


@public_bp.route("/account/orders/<int:order_id>")
@customer_required
def my_order_detail(order_id):
    # customer_id in the WHERE clause: another customer's order gives 404,
    # even if someone types its ID into the URL.
    order = query_one("SELECT * FROM order_summary WHERE order_id = ? AND customer_id = ?",
                      (order_id, g.customer["customer_id"]))
    if order is None:
        abort(404)
    items = query_all("""SELECT oi.quantity, oi.unit_price, p.name, p.brand, c.name AS category,
                                ROUND(oi.quantity * oi.unit_price, 2) AS line_total
                         FROM order_items oi
                         JOIN products p   ON p.product_id = oi.product_id
                         JOIN categories c ON c.category_id = p.category_id
                         WHERE oi.order_id = ?""", (order_id,))
    return render_template("public/my_order_detail.html", order=order, items=items)


@public_bp.route("/register", methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        if query_one("SELECT 1 FROM customers WHERE email = ?", (email,)):
            form.email.errors.append("An account with this email already exists.")
        elif query_one("SELECT 1 FROM customers WHERE phone = ?", (form.phone.data,)):
            form.phone.errors.append("This mobile number is already registered.")
        else:
            try:
                cur = execute("""INSERT INTO customers (full_name, email, phone, password_hash,
                                                       address, city)
                                 VALUES (?, ?, ?, ?, ?, ?)""",
                              (form.full_name.data.strip(), email, form.phone.data,
                               hash_password(form.password.data), form.address.data.strip(),
                               form.city.data.strip()))
            except sqlite3.IntegrityError:          # e.g. two sign-ups at the same moment
                flash("That email or phone number is already registered.", "error")
            else:
                login_customer({"customer_id": cur.lastrowid})
                flash("Welcome! Your account has been created.", "success")
                return redirect(safe_next(url_for("public.products")))
    return render_template("public/register.html", form=form)


@public_bp.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        customer = query_one("SELECT customer_id, password_hash FROM customers WHERE email = ?",
                             (form.email.data.strip().lower(),))
        if customer and verify_password(customer["password_hash"], form.password.data):
            cart = session.get("cart")            # keep a guest's cart after login
            login_customer(customer)
            if cart:
                session["cart"] = cart
            flash("Logged in successfully.", "success")
            return redirect(safe_next(url_for("public.home")))
        # Same message whether the email or the password was wrong,
        # so attackers cannot discover which emails are registered.
        flash("Invalid email or password.", "error")
    return render_template("public/login.html", form=form)


@public_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("public.home"))
