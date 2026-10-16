"""
tests/test_app.py - automated tests.  Run from the project folder:

    python -m pytest -v

Each test gets a fresh copy of a small test database (real products from the
Excel file, demo staff, two customers, every product stocked with 50 units),
so tests never touch your real instance/blinkit.db.
"""
import os
import shutil
import sqlite3
import sys

import pytest
from werkzeug.security import generate_password_hash

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import seed                                   # noqa: E402
from app import create_app                    # noqa: E402
from config import TestConfig                 # noqa: E402

SCHEMA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schema.sql")
P1, P2 = 153019, 11422          # Onions (Aurora LLC), Potatoes (Ramaswamy-Tata)


# ------------------------------------------------------------------ fixtures
@pytest.fixture(scope="session")
def template_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "template.db"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    with open(SCHEMA, encoding="utf-8") as f:
        conn.executescript(f.read())
    with conn:
        seed.load_products(conn)
        seed.load_staff(conn)
        conn.execute("UPDATE products SET stock_qty = 50")
        pwd = generate_password_hash("Customer@123")
        conn.execute("INSERT INTO customers (full_name, email, phone, password_hash, address, city) "
                     "VALUES ('Alice Test', 'alice@example.com', '9000000001', ?, '1 Test Road', 'Pune')", (pwd,))
        conn.execute("INSERT INTO customers (full_name, email, phone, password_hash, address, city) "
                     "VALUES ('Bob Test', 'bob@example.com', '9000000002', ?, '2 Test Road', 'Pune')", (pwd,))
    conn.close()
    return path


@pytest.fixture
def app(template_db, tmp_path):
    db_path = tmp_path / "test.db"
    shutil.copy(template_db, db_path)

    class Cfg(TestConfig):
        DATABASE = str(db_path)
    return create_app(Cfg)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def staff_login(client, who="priya"):
    pwd = {"admin": "Admin@123", "manager": "Manager@123"}.get(who, "Sales@123")
    return client.post("/admin/login", data={"email": f"{who}@blinkit.test", "password": pwd})


def customer_login(client, email="alice@example.com"):
    return client.post("/login", data={"email": email, "password": "Customer@123"})


def new_order(client, items, customer_id=1, **extra):
    data = {"customer_id": customer_id, "order_date": "2026-10-01",
            "payment_method": "upi", "payment_status": "paid", "notes": "",
            "product_id": [str(p) for p, _ in items], "quantity": [str(q) for _, q in items]}
    data.update(extra)
    return client.post("/admin/orders/new", data=data)


def stock(db, pid):
    return db.execute("SELECT stock_qty FROM products WHERE product_id = ?", (pid,)).fetchone()[0]


def count(db, table):
    return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ------------------------------------------------------------ public website
@pytest.mark.parametrize("url", ["/", "/about", "/contact", "/products", "/products?category=1",
                                 f"/products/{P1}", "/item/Onions", "/cart", "/login", "/register",
                                 "/admin/login"])
def test_public_pages_load(client, url):
    assert client.get(url).status_code == 200


def test_unknown_product_is_404(client):
    assert client.get("/products/1").status_code == 404


def test_search_finds_products(client):
    page = client.get("/products?q=Onions").get_data(as_text=True)
    assert "<strong>1</strong> products" in page and "Onions" in page


def test_shop_shows_each_product_name_once(client, db):
    # 268 rows in the products table, but only 51 distinct names (GROUP BY p.name).
    page = client.get("/products").get_data(as_text=True)
    names = db.execute("SELECT COUNT(DISTINCT name) FROM products").fetchone()[0]
    assert f"<strong>{names}</strong> products" in page
    assert page.count("<h3><a href=\"/item/Cheese\">Cheese</a></h3>") == 1


def test_item_page_lists_every_brand_cheapest_first(client, db):
    rows = db.execute("SELECT brand FROM products WHERE name = 'Cheese' ORDER BY price").fetchall()
    page = client.get("/item/Cheese").get_data(as_text=True)
    positions = [page.index(r["brand"].replace("'", "&#39;")) for r in rows]
    assert positions == sorted(positions)               # all brands shown, cheapest first
    assert client.get("/item/NoSuchThing").status_code == 404


def test_sql_injection_in_search_and_sort_is_harmless(client, db):
    r = client.get("/products?q=' OR 1=1 --&sort=name; DROP TABLE products")
    assert r.status_code == 200
    assert "<strong>0</strong> products" in r.get_data(as_text=True)
    assert count(db, "products") == 268          # table still there


# ------------------------------------------------------- registration / login
def test_register_success(client, db):
    r = client.post("/register", data={"full_name": "New Person", "email": "New@Example.com",
                                       "phone": "9123456789", "address": "5 Some Street",
                                       "city": "Delhi", "password": "longpass1", "confirm": "longpass1"})
    assert r.status_code == 302
    row = db.execute("SELECT email, password_hash FROM customers WHERE phone = '9123456789'").fetchone()
    assert row["email"] == "new@example.com"
    assert row["password_hash"] != "longpass1"           # stored hashed, never plain


def test_register_duplicate_email_rejected(client, db):
    before = count(db, "customers")
    r = client.post("/register", data={"full_name": "Copy", "email": "alice@example.com",
                                       "phone": "9123456780", "address": "5 Some Street",
                                       "city": "Delhi", "password": "longpass1", "confirm": "longpass1"})
    assert r.status_code == 200 and b"already exists" in r.data
    assert count(db, "customers") == before


def test_register_missing_fields_and_bad_phone(client, db):
    before = count(db, "customers")
    r = client.post("/register", data={"full_name": "", "email": "x@example.com", "phone": "12345",
                                       "password": "short", "confirm": "nomatch"})
    page = r.get_data(as_text=True)
    assert "This field is required" in page and "10-digit" in page and "Passwords do not match" in page
    assert count(db, "customers") == before


def test_customer_wrong_password(client):
    r = client.post("/login", data={"email": "alice@example.com", "password": "wrong"})
    assert b"Invalid email or password" in r.data


def test_staff_wrong_password(client):
    r = client.post("/admin/login", data={"email": "priya@blinkit.test", "password": "nope"})
    assert b"Invalid email or password" in r.data


# ------------------------------------------------------------ access control
def test_visitor_redirected_from_admin(client):
    r = client.get("/admin/orders")
    assert r.status_code == 302 and "/admin/login" in r.headers["Location"]


def test_customer_cannot_access_admin(client):
    customer_login(client)
    for url in ["/admin/", "/admin/orders", "/admin/customers", "/admin/reports"]:
        r = client.get(url)
        assert r.status_code == 302 and "/admin/login" in r.headers["Location"], url


def test_sales_exec_blocked_from_manager_and_admin_pages(client):
    staff_login(client, "priya")
    assert client.get("/admin/").status_code == 200
    assert client.get("/admin/reports").status_code == 403
    assert client.get("/admin/employees").status_code == 403
    assert client.get(f"/admin/products/{P1}/edit").status_code == 403
    assert client.post("/admin/orders/1/delete").status_code == 403


def test_manager_can_see_reports_but_not_employees(client):
    staff_login(client, "manager")
    assert client.get("/admin/reports").status_code == 200
    assert client.get("/admin/employees").status_code == 403


def test_customer_cannot_view_another_customers_order(client, db):
    staff_login(client)
    new_order(client, [(P1, 1)], customer_id=2)          # Bob's order
    client.post("/admin/logout")
    customer_login(client, "alice@example.com")
    assert client.get("/account/orders/1").status_code == 404


def test_deactivated_employee_loses_access(client, db):
    staff_login(client, "priya")
    assert client.get("/admin/").status_code == 200
    db.execute("UPDATE employees SET is_active = 0 WHERE email = 'priya@blinkit.test'")
    db.commit()
    assert client.get("/admin/").status_code == 302        # kicked out on next request
    r = staff_login(client, "priya")
    assert b"inactive" in r.data


def test_csrf_is_enforced_when_enabled(template_db, tmp_path):
    shutil.copy(template_db, tmp_path / "c.db")

    class Cfg(TestConfig):
        DATABASE = str(tmp_path / "c.db")
        WTF_CSRF_ENABLED = True
    c = create_app(Cfg).test_client()
    r = c.post("/admin/login", data={"email": "priya@blinkit.test", "password": "Sales@123"})
    assert r.status_code == 400                            # no CSRF token -> rejected


# ------------------------------------------------------ Sales Department flow
def test_staff_records_transaction_end_to_end(client, db):
    staff_login(client, "priya")
    # "price" and "total_amount" are extra fields a tampered browser might send.
    r = new_order(client, [(P1, 2), (P2, 3)], price="1", total_amount="1")
    assert r.status_code == 302 and "/admin/orders/1" in r.headers["Location"]

    order = db.execute("SELECT * FROM orders WHERE order_id = 1").fetchone()
    prices = {r["product_id"]: r["price"] for r in
              db.execute("SELECT product_id, price FROM products WHERE product_id IN (?, ?)", (P1, P2))}
    expected = round(prices[P1] * 2 + prices[P2] * 3, 2)
    assert order["total_amount"] == expected                # server-calculated total
    assert order["channel"] == "staff" and order["employee_id"] == 3
    assert count(db, "order_items") == 2
    pay = db.execute("SELECT * FROM payments WHERE order_id = 1").fetchone()
    assert pay["amount"] == expected and pay["status"] == "paid"
    assert stock(db, P1) == 48 and stock(db, P2) == 47

    # ...and it shows up on the dashboard, the list and the detail page.
    assert b"BLK-000001" in client.get("/admin/").data
    assert b"BLK-000001" in client.get("/admin/orders").data
    assert client.get("/admin/orders/1").status_code == 200


def test_same_product_twice_is_merged_into_one_line(client, db):
    staff_login(client)
    new_order(client, [(P1, 2), (P1, 3)])
    row = db.execute("SELECT quantity FROM order_items WHERE order_id = 1").fetchall()
    assert len(row) == 1 and row[0]["quantity"] == 5


@pytest.mark.parametrize("qty", ["0", "-2", "abc", "5000"])
def test_invalid_quantity_rejected(client, db, qty):
    staff_login(client)
    r = new_order(client, [(P1, qty)])
    assert r.status_code == 200                             # form shown again
    assert count(db, "orders") == 0 and stock(db, P1) == 50


def test_order_with_no_products_rejected(client, db):
    staff_login(client)
    r = new_order(client, [("", "")])
    assert b"Add at least one product" in r.data and count(db, "orders") == 0


def test_missing_customer_rejected(client, db):
    staff_login(client)
    r = new_order(client, [(P1, 1)], customer_id=0)
    assert b"Choose a customer" in r.data and count(db, "orders") == 0


def test_future_date_rejected(client, db):
    staff_login(client)
    r = new_order(client, [(P1, 1)], order_date="2099-01-01")
    assert b"cannot be in the future" in r.data and count(db, "orders") == 0


def test_insufficient_stock_rolls_back_everything(client, db):
    staff_login(client)
    # First line is fine, second asks for more than the 50 in stock.
    r = new_order(client, [(P1, 5), (P2, 51)])
    assert b"Not enough stock" in r.data
    assert count(db, "orders") == 0 and count(db, "order_items") == 0 and count(db, "payments") == 0
    assert stock(db, P1) == 50                              # first line's stock change undone


def test_cancel_restores_stock_and_refunds(client, db):
    staff_login(client)
    new_order(client, [(P1, 4)])
    assert stock(db, P1) == 46
    client.post("/admin/orders/1/status", data={"status": "cancelled"})
    assert stock(db, P1) == 50
    assert db.execute("SELECT status FROM payments WHERE order_id = 1").fetchone()[0] == "refunded"


def test_delivered_order_cannot_be_reopened(client, db):
    staff_login(client)
    new_order(client, [(P1, 1)])
    client.post("/admin/orders/1/status", data={"status": "delivered"})
    r = client.post("/admin/orders/1/status", data={"status": "placed"}, follow_redirects=True)
    assert b"cannot be changed" in r.data
    assert db.execute("SELECT status FROM orders WHERE order_id = 1").fetchone()[0] == "delivered"


def test_manager_deletes_order_and_stock_returns(client, db):
    staff_login(client, "manager")
    new_order(client, [(P1, 3)])
    client.post("/admin/orders/1/delete")
    assert count(db, "orders") == 0 and count(db, "order_items") == 0 and count(db, "payments") == 0
    assert stock(db, P1) == 50


def test_customer_with_orders_cannot_be_deleted(client, db):
    staff_login(client, "manager")
    new_order(client, [(P1, 1)], customer_id=1)
    r = client.post("/admin/customers/1/delete", follow_redirects=True)
    assert b"cannot be deleted" in r.data
    assert db.execute("SELECT 1 FROM customers WHERE customer_id = 1").fetchone()


def test_staff_creates_customer_duplicate_phone_rejected(client, db):
    staff_login(client)
    r = client.post("/admin/customers/new", data={"full_name": "Walk In", "email": "walkin@example.com",
                                                  "phone": "9000000001", "address": "Shop counter",
                                                  "city": "Pune"})
    assert b"already uses this mobile" in r.data


def test_product_mrp_below_price_rejected(client, db):
    staff_login(client, "manager")
    r = client.post(f"/admin/products/{P1}/edit", data={
        "name": "Onions", "brand": "Aurora LLC", "category_id": 1, "price": "100", "mrp": "90",
        "stock_qty": "10", "min_stock": "5", "max_stock": "50", "is_active": "y"})
    assert b"MRP cannot be lower" in r.data


def test_price_change_does_not_rewrite_old_orders(client, db):
    staff_login(client, "manager")
    new_order(client, [(P1, 1)])
    old = db.execute("SELECT unit_price FROM order_items WHERE order_id = 1").fetchone()[0]
    client.post(f"/admin/products/{P1}/edit", data={
        "name": "Onions", "brand": "Aurora LLC", "category_id": 6, "price": "10", "mrp": "20",
        "stock_qty": "10", "min_stock": "5", "max_stock": "88", "is_active": "y"})
    assert db.execute("SELECT price FROM products WHERE product_id = ?", (P1,)).fetchone()[0] == 10
    assert db.execute("SELECT unit_price FROM order_items WHERE order_id = 1").fetchone()[0] == old


# ------------------------------------------------------------ customer checkout
def test_customer_cart_and_checkout(client, db):
    client.post("/cart/add", data={"product_id": P1, "quantity": 2})   # as a guest
    assert client.get("/checkout").status_code == 302                  # must log in
    customer_login(client)
    assert b"Onions" in client.get("/cart").data                        # cart kept after login
    r = client.post("/checkout", data={"payment_method": "cod", "notes": "Ring the bell"})
    assert r.status_code == 302
    order = db.execute("SELECT * FROM order_summary WHERE order_id = 1").fetchone()
    assert order["channel"] == "online" and order["employee_id"] is None
    assert order["payment_status"] == "pending"                         # cash on delivery
    assert stock(db, P1) == 48
    assert b"BLK-000001" in client.get("/account/orders").data


def test_cannot_add_more_than_stock_to_cart(client):
    r = client.post("/cart/add", data={"product_id": P1, "quantity": 51}, follow_redirects=True)
    assert b"only 50" in r.data


def test_reports_revenue_matches_raw_sql(client, db):
    staff_login(client, "manager")
    new_order(client, [(P1, 2)])
    new_order(client, [(P2, 1)])
    client.post("/admin/orders/2/status", data={"status": "cancelled"})
    expected = db.execute("SELECT SUM(total_amount) FROM orders WHERE status != 'cancelled'").fetchone()[0]
    from app import inr
    assert inr(expected).encode() in client.get("/admin/reports").data
