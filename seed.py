"""
seed.py - builds the database from scratch.

    python seed.py              # reset: schema + products + staff + sample customers/orders
    python seed.py --no-sample  # reset: schema + products + staff only
    python seed.py --ensure     # create/rebuild only if the database schema is missing

What it does:
  1. Runs schema.sql (drops and recreates every table).
  2. Reads data/blinkit_dataset.xlsx with pandas and loads 11 categories and
     268 products.
  3. Creates demo staff accounts (one per role).
  4. Generates SYNTHETIC customers and orders so the dashboard and reports
     have something to show. Every generated row has is_sample = 1, and the
     website labels them as demo data. They are NOT real Blinkit records.

The random generator is seeded (random.seed(42)), so everyone who runs this
gets exactly the same sample data.
"""
import os
import random
import shutil
import sqlite3
import sys
from datetime import date, datetime, timedelta

import pandas as pd
from werkzeug.security import generate_password_hash

from config import BASE_DIR, Config

EXCEL_PATH = os.path.join(BASE_DIR, "data", "blinkit_dataset.xlsx")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

STAFF = [  # (name, email, role, password) - demo logins, printed at the end
    ("Asha Verma",   "admin@blinkit.test",   "admin",      "Admin@123"),
    ("Rohan Mehta",  "manager@blinkit.test", "manager",    "Manager@123"),
    ("Priya Nair",   "priya@blinkit.test",   "sales_exec", "Sales@123"),
    ("Karan Singh",  "karan@blinkit.test",   "sales_exec", "Sales@123"),
    ("Neha Joshi",   "neha@blinkit.test",    "sales_exec", "Sales@123"),
]
DEMO_CUSTOMER = ("Demo Customer", "demo@example.com", "9876500000", "Customer@123")
REQUIRED_SCHEMA_OBJECTS = {
    "categories", "products", "customers", "employees", "orders",
    "order_items", "payments", "order_summary",
}

FIRST = ["Aarav", "Vivaan", "Aditya", "Ishaan", "Arjun", "Sai", "Reyansh", "Kabir", "Ananya",
         "Diya", "Saanvi", "Aadhya", "Myra", "Kiara", "Meera", "Riya", "Rahul", "Sneha",
         "Vikram", "Pooja", "Nikhil", "Divya", "Siddharth", "Kavya", "Harsh", "Tanvi",
         "Manish", "Shreya", "Varun", "Lakshmi"]
LAST = ["Sharma", "Patel", "Reddy", "Iyer", "Gupta", "Khan", "Das", "Menon", "Rao", "Kulkarni",
        "Chatterjee", "Malhotra", "Bose", "Pillai", "Agarwal", "Naidu", "Fernandes", "Saxena"]
CITIES = ["Gurugram", "New Delhi", "Noida", "Mumbai", "Bengaluru", "Hyderabad", "Pune",
          "Chennai", "Kolkata", "Ahmedabad", "Jaipur", "Lucknow"]
STREETS = ["MG Road", "Park Street", "Sector 29", "Linking Road", "Indiranagar 100ft Road",
           "Banjara Hills Rd 12", "FC Road", "Anna Nagar 2nd Ave", "Civil Lines", "Ring Road"]

# How often each category appears in a basket (fresh food sells most).
CATEGORY_WEIGHT = {
    "Fruits & Vegetables": 10, "Dairy & Breakfast": 10, "Snacks & Munchies": 7,
    "Cold Drinks & Juices": 6, "Grocery & Staples": 6, "Instant & Frozen Food": 5,
    "Household Care": 4, "Personal Care": 4, "Baby Care": 2, "Pet Care": 2, "Pharmacy": 3,
}


def load_products(conn):
    df = pd.read_excel(EXCEL_PATH, sheet_name="blinkit_products")
    df = df.dropna(subset=["product_id", "product_name", "category", "price", "mrp"])

    # --- categories: margin and shelf life must be identical within a category.
    #     If this check passes, moving them to `categories` loses no information (3NF).
    cat_ids = {}
    for name, grp in df.groupby("category"):
        if grp["margin_percentage"].nunique() != 1 or grp["shelf_life_days"].nunique() != 1:
            sys.exit(f"Category {name} has mixed margins/shelf life - cannot normalise.")
        cur = conn.execute(
            "INSERT INTO categories (name, standard_margin_pct, shelf_life_days) VALUES (?, ?, ?)",
            (name, int(grp["margin_percentage"].iloc[0]), int(grp["shelf_life_days"].iloc[0])))
        cat_ids[name] = cur.lastrowid

    rows = [(int(r.product_id), r.product_name.strip(), r.brand.strip(), cat_ids[r.category],
             round(float(r.price), 2), round(float(r.mrp), 2), 0,
             int(r.min_stock_level), int(r.max_stock_level))
            for r in df.itertuples()]
    conn.executemany(
        "INSERT INTO products (product_id, name, brand, category_id, price, mrp, stock_qty, "
        "min_stock, max_stock) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return len(cat_ids), len(rows)


def load_staff(conn):
    for name, email, role, pwd in STAFF:
        conn.execute("INSERT INTO employees (full_name, email, password_hash, role) "
                     "VALUES (?, ?, ?, ?)", (name, email, generate_password_hash(pwd), role))


def make_customers(conn, n=60):
    # One shared hash keeps seeding fast; every sample customer's password is Customer@123.
    pwd_hash = generate_password_hash(DEMO_CUSTOMER[3])
    name, email, phone, _ = DEMO_CUSTOMER
    conn.execute("INSERT INTO customers (full_name, email, phone, password_hash, address, city, "
                 "created_at, is_sample) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                 (name, email, phone, pwd_hash, "12 MG Road", "Gurugram", "2026-05-01 10:00:00"))
    used_phones, used_emails = {phone}, {email}
    for i in range(n - 1):
        first, last = random.choice(FIRST), random.choice(LAST)
        email = f"{first}.{last}{i + 1}@example.com".lower()   # example.com = reserved test domain
        phone = None
        while phone is None or phone in used_phones:
            phone = random.choice("6789") + "".join(random.choices("0123456789", k=9))
        used_phones.add(phone)
        used_emails.add(email)
        created = datetime(2026, 4, 1) + timedelta(days=random.randint(0, 60))
        conn.execute("INSERT INTO customers (full_name, email, phone, password_hash, address, "
                     "city, created_at, is_sample) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                     (f"{first} {last}", email, phone, pwd_hash,
                      f"{random.randint(1, 250)}, {random.choice(STREETS)}",
                      random.choice(CITIES), created.strftime("%Y-%m-%d %H:%M:%S")))


def make_orders(conn, n_orders=480, days=120):
    products = conn.execute("""SELECT p.product_id, p.price, c.name AS category
                               FROM products p JOIN categories c USING (category_id)""").fetchall()
    # Each product gets a popularity score; ~10 products never sell (for the
    # "products never sold" report).
    never = set(random.sample([p[0] for p in products], 10))
    weights = [0 if p[0] in never else CATEGORY_WEIGHT[p[2]] * random.uniform(0.3, 1.7)
               for p in products]
    customers = [r[0] for r in conn.execute("SELECT customer_id FROM customers")]
    cust_weights = [random.uniform(0.2, 3) for _ in customers]     # some loyal customers
    staff = [r[0] for r in conn.execute(
        "SELECT employee_id FROM employees WHERE role IN ('sales_exec', 'manager')")]
    today = date.today()

    for _ in range(n_orders):
        # random() ** 1.3 skews offsets towards 0, so recent weeks get more
        # orders - the charts show a gentle growth trend.
        offset = int(days * (random.random() ** 1.3))
        day = today - timedelta(days=offset)
        stamp = datetime.combine(day, datetime.min.time()) + timedelta(
            hours=random.randint(7, 22), minutes=random.randint(0, 59), seconds=random.randint(0, 59))
        if stamp > datetime.now():
            stamp = datetime.now() - timedelta(minutes=random.randint(5, 300))

        basket = {}
        for p in random.choices(products, weights=weights, k=random.randint(1, 5)):
            basket[p[0]] = (basket.get(p[0], (0, p[1]))[0] + random.randint(1, 3), p[1])
        total = round(sum(q * price for q, price in basket.values()), 2)

        channel = "online" if random.random() < 0.55 else "staff"
        employee = random.choice(staff) if channel == "staff" else None
        age = (today - stamp.date()).days
        if age <= 1:
            status = random.choices(["placed", "delivered"], [0.6, 0.4])[0]
        else:
            status = random.choices(["delivered", "cancelled", "placed"], [0.9, 0.07, 0.03])[0]
        method = random.choice(["upi", "card", "cod"] if channel == "online"
                               else ["upi", "card", "cash"])
        if status == "delivered":
            pay = "paid"
        elif status == "cancelled":
            pay = "refunded" if method in ("upi", "card") else "pending"
        else:
            pay = "pending" if method in ("cod", "cash") else "paid"

        cur = conn.execute(
            "INSERT INTO orders (customer_id, employee_id, channel, order_date, status, "
            "total_amount, is_sample, created_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
            (random.choices(customers, cust_weights)[0], employee, channel,
             stamp.strftime("%Y-%m-%d %H:%M:%S"), status, total, stamp.strftime("%Y-%m-%d %H:%M:%S")))
        oid = cur.lastrowid
        conn.executemany("INSERT INTO order_items (order_id, product_id, quantity, unit_price) "
                         "VALUES (?, ?, ?, ?)", [(oid, pid, q, pr) for pid, (q, pr) in basket.items()])
        conn.execute("INSERT INTO payments (order_id, method, status, amount, paid_at) "
                     "VALUES (?, ?, ?, ?, ?)",
                     (oid, method, pay, total,
                      stamp.strftime("%Y-%m-%d %H:%M:%S") if pay in ("paid", "refunded") else None))


def set_stock(conn):
    """Current stock is not in the dataset, so generate it between 0 and max_stock.
    About 1 in 8 products ends up at or below its reorder level."""
    for pid, lo, hi in conn.execute("SELECT product_id, min_stock, max_stock FROM products").fetchall():
        r = random.random()
        if r < 0.03:
            qty = 0
        elif r < 0.13:
            qty = random.randint(1, lo)
        else:
            qty = random.randint(lo + 1, hi)
        conn.execute("UPDATE products SET stock_qty = ? WHERE product_id = ?", (qty, pid))


def database_is_initialized():
    """Return whether the configured SQLite file has the complete project schema."""
    if not os.path.isfile(Config.DATABASE):
        return False
    conn = None
    try:
        conn = sqlite3.connect(Config.DATABASE)
        objects = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")}
    except sqlite3.Error:
        return False
    finally:
        if conn is not None:
            conn.close()
    return REQUIRED_SCHEMA_OBJECTS.issubset(objects)


def main():
    sample = "--no-sample" not in sys.argv
    random.seed(42)
    os.makedirs(os.path.dirname(Config.DATABASE), exist_ok=True)

    if "--ensure" in sys.argv and database_is_initialized():
        print(f"Database is ready: {Config.DATABASE}")
        return
    if "--ensure" in sys.argv and os.path.exists(Config.DATABASE):
        backup = f"{Config.DATABASE}.uninitialized-{datetime.now():%Y%m%d%H%M%S}.bak"
        shutil.copy2(Config.DATABASE, backup)
        print(f"Uninitialized database backed up to: {backup}")

    if os.path.exists(Config.DATABASE):
        os.remove(Config.DATABASE)

    conn = sqlite3.connect(Config.DATABASE)
    conn.execute("PRAGMA foreign_keys = ON")
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())

    with conn:                                   # one transaction for the whole load
        n_cat, n_prod = load_products(conn)
        load_staff(conn)
        set_stock(conn)
        if sample:
            make_customers(conn)
            make_orders(conn)

    count = lambda t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"Database created: {Config.DATABASE}")
    for t in ("categories", "products", "employees", "customers", "orders", "order_items", "payments"):
        print(f"  {t:<12} {count(t):>5} rows")
    if sample:
        print("  (customers and orders are SYNTHETIC sample data, is_sample = 1)")
    print("\nDemo logins")
    print("  Staff  ->  http://127.0.0.1:5000/admin/login")
    for name, email, role, pwd in STAFF:
        print(f"     {role:<11} {email:<26} {pwd}")
    if sample:
        print("  Customer -> http://127.0.0.1:5000/login")
        print(f"     {DEMO_CUSTOMER[1]:<38} {DEMO_CUSTOMER[3]}")
    conn.close()


if __name__ == "__main__":
    main()
