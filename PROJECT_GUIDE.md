# Blinkit Sales Portal: Project Guide

This guide explains the whole project: how to run it, how the pieces fit together, why each design decision was made, and what you will be asked in your viva. Read it alongside the code. Every file also has comments explaining its important lines.

**Contents**

1. Run it in 5 minutes
2. The big picture
3. Folder structure: what every file does
4. The database
5. How Flask connects Python to the database
6. The Sales Department workflow, step by step
7. Login, roles and access control
8. Security features
9. The customer website
10. Testing
11. Troubleshooting
12. 5-minute demo script for your evaluation
13. Limitations and future enhancements
14. Viva questions and answers
15. About the data

---

## 1. Run it in 5 minutes

**Easiest way: double-click `start_windows.bat`** (on a Mac, `start_mac.command`; if macOS blocks it, right-click it → Open → Open). It does every step below for you on the first run (about 2 minutes) and opens the website in your browser. Keep its black window open while you use the site; closing it stops the website. To reset the demo data, double-click `reset_database_windows.bat`.

**Don't double-click `app.py` or any other `.py` file.** The window flashes and closes because the program stops at its first error (usually that Flask isn't installed yet), and you never see the message. Use the start file, or the commands below.

The manual way: you need **Python 3.10 or newer** ([python.org](https://www.python.org/downloads/); on Windows, tick "Add Python to PATH" during installation). Open a terminal in the project folder (the one containing `app.py`).

**Windows (Command Prompt or PowerShell)**

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python seed.py
python app.py
```

**macOS / Linux**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 seed.py
python3 app.py
```

What each line does:

| Command | What it does |
|---|---|
| `python -m venv venv` | Creates a private folder of Python packages just for this project |
| `activate` | Switches the terminal to use that folder. You'll see `(venv)` in the prompt |
| `pip install -r requirements.txt` | Installs Flask, Flask-WTF, pandas, openpyxl, python-dotenv, pytest |
| `copy .env.example .env` | Creates your settings file. Open `.env` and change `SECRET_KEY` to any long random text |
| `python seed.py` | Builds `instance/blinkit.db` from `schema.sql` and your Excel file |
| `python app.py` | Starts the web server |

Expected output of `seed.py`:

```
Database created: .../instance/blinkit.db
  categories      11 rows
  products       268 rows
  employees        5 rows
  customers       60 rows
  orders         480 rows
  order_items   1442 rows
  payments       480 rows
  (customers and orders are SYNTHETIC sample data, is_sample = 1)
```

Then open **http://127.0.0.1:5000** in your browser. Stop the server with `Ctrl + C`.

**Demo logins**

| Interface | URL | Email | Password | Role |
|---|---|---|---|---|
| Customer site | /login | demo@example.com | Customer@123 | Customer |
| Staff dashboard | /admin/login | priya@blinkit.test | Sales@123 | Sales Executive |
| Staff dashboard | /admin/login | manager@blinkit.test | Manager@123 | Sales Manager |
| Staff dashboard | /admin/login | admin@blinkit.test | Admin@123 | Administrator |

Running `python seed.py` again resets everything to this starting state. Use it before your demo.

---

## 2. The big picture

```
                 ┌──────────────────────────────┐
  Customer  ───► │  Public website  /, /products │
                 │  templates/public/*.html      │
                 └──────────────┬───────────────┘
                                │ HTTP request (GET / POST)
                 ┌──────────────▼───────────────┐
                 │  Flask app (app.py)           │
                 │  routes/public.py  (shop)     │
                 │  routes/admin.py   (/admin)   │
                 │  auth.py  forms.py  services.py│
                 └──────────────┬───────────────┘
                                │ SQL with ? placeholders (db.py)
                 ┌──────────────▼───────────────┐
                 │  SQLite database              │
                 │  instance/blinkit.db          │
                 └──────────────▲───────────────┘
                                │
                 ┌──────────────┴───────────────┐
  Employee  ───► │  Internal dashboard /admin/...│
                 │  templates/admin/*.html       │
                 └──────────────────────────────┘
```

There are **two interfaces but one application and one database**. The customer website and the staff dashboard read and write the same tables. What keeps them apart is **access control** in Python: decorators on every route, plus `WHERE customer_id = ?` on every customer query.

**The browser never talks to the database.** Every request goes through a Flask route function, which decides what SQL to run and which HTML template to show. This is the data flow your brief asks you to explain:

```
User action → HTML form → Flask route → Python validation → SQL query → SQLite
           ← updated webpage ← Jinja2 template ← Flask response ← query result
```

The data-flow diagram for the sales workflow is in `docs/dataflow.png`.

**Technologies and why they were chosen**

| Layer | Technology | Why |
|---|---|---|
| Database | SQLite | One file, nothing to install, full SQL support (joins, constraints, transactions, views) |
| Backend | Python + Flask | Flask is small enough to understand completely; you write the SQL yourself |
| Forms | Flask-WTF / WTForms | Validation rules in one place, automatic CSRF protection |
| Templates | Jinja2 (built into Flask) | Puts database results into HTML; escapes output automatically |
| Frontend | HTML, CSS, a little JavaScript | No framework to learn; responsive CSS works on phones |
| Charts | Chart.js 4.4.1 (bundled in `static/js`) | Works offline during your demo |
| Data loading | pandas + openpyxl | Reads your Excel file in a few lines |
| Testing | pytest | 48 automated tests |

**SQLite or MySQL?**

| | SQLite (used here) | MySQL |
|---|---|---|
| Setup | None. The database is one file | Install and run a server, create users |
| Good for | Prototypes, demos, single-user apps, phones | Many simultaneous users, production websites |
| Concurrency | One writer at a time | Many writers |
| Moving the project | Copy the folder | Export and import the database |
| SQL features used here | All supported | All supported |

For a college demo, SQLite removes a whole category of setup problems. If your syllabus requires MySQL, the changes are small: install `PyMySQL`, change `get_db()` in `db.py` to `pymysql.connect(...)`, change the `?` placeholders to `%s`, and change `INTEGER PRIMARY KEY AUTOINCREMENT` to `INT AUTO_INCREMENT PRIMARY KEY` in the schema.

---

## 3. Folder structure: what every file does

```
blinkit_project/
├── app.py              Creates the Flask app, registers both blueprints, error pages, filters
├── config.py           Settings: SECRET_KEY from .env, database path, CSRF on
├── db.py               Opens/closes the database connection; query helpers
├── auth.py             Password hashing, login/session, @staff_required, @customer_required
├── forms.py            Every form and its validation rules (Flask-WTF)
├── services.py         Business rules: create_order (one transaction), status changes, delete
├── catalog.py          Product emoji icons (the dataset has no photos)
├── routes/
│   ├── public.py       Customer pages: home, products, cart, checkout, my orders, login
│   └── admin.py        Staff pages: dashboard, transactions, customers, products, reports
├── schema.sql          CREATE TABLE statements, constraints, indexes, a VIEW
├── seed.py             Builds the DB: runs schema.sql, loads Excel, adds demo data
├── queries.sql         SQL practice: SELECT, JOIN, GROUP BY, HAVING, subqueries, CRUD
├── requirements.txt    Python packages to install
├── .env.example        Template for your secret settings (copy to .env)
├── data/
│   └── blinkit_dataset.xlsx   Your dataset (268 products)
├── instance/
│   └── blinkit.db      The SQLite database (created by seed.py, not shared)
├── templates/
│   ├── _macros.html    Reusable pieces: form field, status badge, pagination, flash messages
│   ├── error.html      403 / 404 / 500 pages
│   ├── public/         13 customer templates (base layout, product card, pages)
│   └── admin/          14 staff templates (sidebar layout, login, pages)
├── static/
│   ├── css/public.css  Shop styling (cream, green, tangerine)
│   ├── css/admin.css   Dashboard styling (dark sidebar, deliberately different)
│   ├── js/admin.js     Charts, order-form rows, live estimate, delete confirmation
│   └── js/chart.umd.min.js  Chart.js library (MIT licence)
├── tests/
│   └── test_app.py     48 automated tests
└── docs/
    ├── erd.png / erd.dot           Entity-relationship diagram
    ├── dataflow.png / dataflow.dot Data-flow diagram of a sale
    └── screenshots/                Screenshots of every main page for your report
```

---

## 4. The database

### 4.1 Starting from your dataset

Your Excel file has one sheet with 268 rows and these columns:

`product_id, product_name, category, brand, price, mrp, margin_percentage, shelf_life_days, min_stock_level, max_stock_level`

Two things stand out when you look closely:

1. **`margin_percentage` and `shelf_life_days` depend on the category, not the product.** Every Dairy item has a 20% margin and 7-day shelf life; every Snack has 35% and 90 days. `seed.py` checks this and refuses to load the data if any category is inconsistent.
2. **`margin_percentage` is also calculable:** it always equals `(mrp - price) / mrp × 100`. Query D6 in `queries.sql` proves it for all 268 rows.

Keeping these columns in the products table would repeat the same value 30 times for Dairy. That is a **transitive dependency** (product_id → category → margin), which breaks Third Normal Form. So they move to the `categories` table. This is your best example for the viva question on normalization.

### 4.2 The seven tables

The diagram is in `docs/erd.png`.

| Table | Purpose | Key | Rows after seeding |
|---|---|---|---|
| `categories` | 11 product groups with their standard margin and shelf life | category_id | 11 |
| `products` | What is sold: name, brand, price, MRP, stock levels | product_id (from Excel) | 268 |
| `customers` | People who buy, online or through staff | customer_id | 60 |
| `employees` | Staff logins with a role | employee_id | 5 |
| `orders` | One row per sales transaction (header) | order_id = transaction ID | 480 |
| `order_items` | Which products, how many, at what price | (order_id, product_id) | ~1,440 |
| `payments` | Simulated payment for each order | payment_id; order_id UNIQUE | 480 |

**Why every table is needed**

- An order can contain many products, and a product can be in many orders. That is a **many-to-many** relationship, which a relational database cannot store directly. `order_items` is the **junction table** that resolves it.
- `payments` is separate from `orders` because payment has its own life cycle (pending → paid → refunded) and its own attributes (method, paid_at). It is **one-to-one** with orders: `order_id` is UNIQUE in payments.
- `customers` and `employees` are separate because they log in to different interfaces and have different attributes. Keeping them apart makes it impossible for a customer account to reach `/admin` by accident.

**Tables deliberately not created** (and why you can defend that):

- **Roles table:** only three fixed roles exist, so a CHECK constraint (`role IN ('sales_exec', 'manager', 'admin')`) does the job without an extra join.
- **Separate inventory table:** stock is one number per product and depends only on product_id, so it fits in `products`. You would add an inventory table only if there were several stores or warehouses.
- **Brands table:** 267 of the 268 brands are unique, so a lookup table would save nothing.

### 4.3 Relationships

| Relationship | Type | How it is enforced |
|---|---|---|
| categories → products | One-to-many | `products.category_id REFERENCES categories` |
| customers → orders | One-to-many | `orders.customer_id REFERENCES customers` |
| employees → orders | One-to-many, optional | `orders.employee_id` may be NULL (online orders) |
| orders ↔ products | Many-to-many | Through `order_items` |
| orders → payments | One-to-one | `payments.order_id` is `UNIQUE` |

### 4.4 Constraints: the database protects itself

Even if the Python code had a bug, the database rejects bad data:

| Constraint | Example in schema.sql | What it prevents |
|---|---|---|
| PRIMARY KEY | `order_id INTEGER PRIMARY KEY AUTOINCREMENT` | Two rows with the same ID |
| FOREIGN KEY | `customer_id ... REFERENCES customers(customer_id)` | An order for a customer who doesn't exist |
| ON DELETE RESTRICT | on `orders.customer_id` | Deleting a customer who has sales history |
| ON DELETE CASCADE | on `order_items.order_id` | Orphan line items when an order is deleted |
| NOT NULL | `full_name TEXT NOT NULL` | Missing required data |
| UNIQUE | `email ... UNIQUE`, `UNIQUE (name, brand)` | Duplicate accounts and duplicate products |
| CHECK | `mrp >= price`, `quantity BETWEEN 1 AND 1000`, `stock_qty >= 0` | Impossible values |
| CHECK (multi-column) | online orders have no employee; staff orders must have one | Inconsistent records |
| DEFAULT | `status DEFAULT 'placed'`, `created_at DEFAULT (datetime('now','localtime'))` | Having to fill obvious values |
| Composite PK | `PRIMARY KEY (order_id, product_id)` | The same product twice in one order |

> SQLite only enforces foreign keys when you run `PRAGMA foreign_keys = ON` on each connection. `db.py` does this every time. It's a good detail to mention in your viva.

### 4.5 Indexes

An index is like the index at the back of a book: the database can jump to matching rows instead of reading every row. Indexes are created on columns that are searched, filtered, joined or sorted often: `products(category_id)`, `products(name)`, `orders(customer_id)`, `orders(employee_id)`, `orders(order_date)`, `orders(status)`, `order_items(product_id)`, `customers(full_name)`. Primary keys and UNIQUE columns get indexes automatically.

The trade-off: indexes speed up reads but slightly slow down inserts and updates, so we only index columns that are actually queried.

### 4.6 Normalization summary

- **1NF:** every column holds one value, and every table has a primary key. There are no lists in a cell: products in an order are separate rows in `order_items`.
- **2NF:** in `order_items`, whose key is (order_id, product_id), every non-key column (quantity, unit_price) depends on the *whole* key, not just one part.
- **3NF:** no non-key column depends on another non-key column. Margin and shelf life moved to `categories`. Customer names are not copied into orders; they are reached by a JOIN.

**Two deliberate stored values you should be ready to justify:**

- `order_items.unit_price` looks like a copy of `products.price`, but it isn't. It records the price *at the time of sale*. When a manager changes a price, old orders must not change. There is a test for this.
- `orders.total_amount` could be calculated from the items, but it is stored as an audited snapshot: it's calculated once, in Python, inside the same transaction as the items, and never edited afterwards. This also makes reports faster. The test `test_staff_records_transaction_end_to_end` checks it always equals the sum of the items.

### 4.7 The VIEW

`order_summary` is a saved SELECT that joins orders, customers, employees and payments. The transaction list, customer history and "My orders" pages all read from it, so the join is written once. A view stores no data; it runs its query whenever it is used.

---

## 5. How Flask connects Python to the database

### 5.1 The connection (`db.py`)

```python
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db
```

- `sqlite3` is built into Python, so there's nothing extra to install.
- `g` is Flask's per-request storage. One connection is opened per request and reused by every query in that request.
- `row_factory = sqlite3.Row` lets you write `row["name"]` instead of `row[1]`, and templates can write `{{ p.name }}`.
- `close_db()` is registered with `app.teardown_appcontext`, so the connection always closes when the request ends, even if there was an error.

### 5.2 One complete request: the products page

1. The user visits `/products?q=milk&sort=price_asc`.
2. Flask matches the URL to this function in `routes/public.py`:

```python
@public_bp.route("/products")
def products():
    q = request.args.get("q", "").strip()            # read ?q= from the URL
    ...
    sql = """SELECT p.product_id, p.name, p.brand, p.price, p.mrp, p.stock_qty,
                    c.name AS category
             FROM products p JOIN categories c ON c.category_id = p.category_id
             WHERE p.is_active = 1"""
    params = []
    if q:
        sql += " AND (p.name LIKE ? OR p.brand LIKE ? OR c.name LIKE ?)"
        params += [f"%{q}%"] * 3                     # values go in params, never in the SQL text
    ...
    rows = query_all(sql, params)                    # run it
    return render_template("public/products.html", products=rows, ...)
```

3. The template loops over the rows:

```html
{% for p in products %}{{ product_card(p) }}{% endfor %}
```

4. Flask sends the finished HTML back to the browser.

Every page in the project follows this same **URL → function → SQL → template** pattern.

### 5.3 Blueprints

A blueprint is a group of routes. `public_bp` holds the shop, and `admin_bp` is registered with `url_prefix="/admin"`, so every staff URL starts with `/admin`. This keeps the two interfaces in separate files while sharing one app, one config and one database.

---

## 6. The Sales Department workflow, step by step

This is the workflow your brief asks for. Try it while reading.

| Step | What happens | Where in the code |
|---|---|---|
| 1. Log in | Employee enters email and password at `/admin/login`. The password is checked against the stored hash. | `admin.login()`, `auth.verify_password()` |
| 2. Open dashboard | KPI cards, 30-day chart, category chart, recent transactions and low-stock list, all from SQL aggregates | `admin.dashboard()` |
| 3. Choose or create a customer | Pick from the dropdown, or "Create a new customer", which returns you to the form with that customer pre-selected | `admin.order_new()`, `admin.customer_new()` |
| 4. Choose products | Add rows with "+ Add product". JavaScript shows the price, stock and a live estimate. | `order_form.html`, `admin.js` |
| 5. Enter details | Quantity, transaction date, payment method and status, notes | `forms.OrderForm` |
| 6. Submit | The form is POSTed with a hidden CSRF token | |
| 7. Flask validates | Required fields, date not in future, customer chosen, quantities are whole numbers from 1 to 1000, duplicate rows merged | `form.validate_on_submit()`, `services.parse_items()` |
| 8. Database stores it | `create_order()` reads real prices, calculates the total, and inserts the order, items and payment, plus reduces stock, all in **one transaction** | `services.create_order()` |
| 9. Dashboard shows it | Redirect to the transaction page. It also appears at the top of Recent transactions. | `admin.order_detail()` |
| 10. Reports update | Reports are live SQL queries, so the new sale is included immediately | `admin.reports()` |

### How transaction IDs are generated

`orders.order_id` is `INTEGER PRIMARY KEY AUTOINCREMENT`. SQLite assigns the next number when the row is inserted, and Python reads it with `cursor.lastrowid`. `AUTOINCREMENT` guarantees an ID is never reused, even after a delete, so a transaction number always refers to one sale. The website displays it as `BLK-000042` using the `order_code` filter in `app.py`.

### How totals are calculated

The browser only sends **product IDs and quantities**. The order form's `data-price` attributes exist only for the live estimate. In `create_order()`:

```python
rows = db.execute("SELECT product_id, name, brand, price, stock_qty, is_active "
                  "FROM products WHERE product_id IN (?,?,...)", ids)
total = sum(product["price"] * qty ...)        # prices from the DATABASE
```

Even if someone edits the HTML, or sends a fake `price` or `total_amount` field, the server ignores it. The test `test_staff_records_transaction_end_to_end` sends exactly that kind of fake field and checks that it's ignored.

### How the transaction stays consistent

```python
with db:                       # BEGIN
    INSERT INTO orders ...
    for each product:
        INSERT INTO order_items ...
        UPDATE products SET stock_qty = stock_qty - ?
               WHERE product_id = ? AND stock_qty >= ?
        if no row was updated: raise OrderError("Not enough stock")
    INSERT INTO payments ...
                               # COMMIT if we reach here, ROLLBACK on any exception
```

If the third product is out of stock, the order row and the first two items that were already inserted are **rolled back**. Nothing half-finished is left behind. The test `test_insufficient_stock_rolls_back_everything` proves it.

Putting the stock check inside the UPDATE (`AND stock_qty >= ?`) makes check-and-update a single step, so two people selling the last item at the same moment cannot both succeed.

### How invalid and duplicate entries are prevented

| Problem | Prevented by |
|---|---|
| Missing customer, date or product | WTForms `DataRequired`, and `parse_items` rejects an empty list |
| Quantity 0, negative, text, or huge | `parse_items()`, plus `CHECK (quantity BETWEEN 1 AND 1000)` in the schema |
| Future date | `OrderForm.validate_order_date` |
| Same product entered twice | Rows are merged in `parse_items()`; the composite primary key blocks duplicates anyway |
| Double-click or refresh resubmitting the form | **Post/Redirect/Get**: after saving, the browser is redirected, so refresh reloads the detail page and doesn't re-POST |
| Duplicate customer | UNIQUE email and phone, checked with a friendly message first |
| Selling more than in stock | Conditional UPDATE and rollback |
| Product that doesn't exist or is hidden | Checked in `create_order()`, plus the foreign key |

### After the sale

- **Status:** Placed → Delivered, or Placed → Cancelled. Delivered and cancelled are final (`ALLOWED_STATUS_CHANGES`).
- **Cancelling** puts the stock back and marks a paid payment as refunded, in one transaction.
- **Deleting** (managers only) restores stock, then `ON DELETE CASCADE` removes the items and payment.

---

## 7. Login, roles and access control

### Passwords

```python
generate_password_hash("Sales@123")   # -> 'scrypt:32768:8:1$Xy...$9f3a...'
check_password_hash(stored, typed)    # -> True / False
```

The database stores only the hash. A hash is one-way: you can check a password against it, but you can't turn it back into the password. A random **salt** is added, so two people with the same password get different hashes.

### Sessions

After login, three facts go into Flask's `session`: `user_type`, `user_id` and `role`. Flask stores the session in a cookie that is **signed** with `SECRET_KEY`. The user can read it, but if they change it the signature no longer matches and Flask throws it away. On every request, `auth.load_logged_in_user()` reloads the user from the database, so a deactivated employee is locked out immediately.

### Roles

| Feature | Visitor | Customer | Sales Executive | Sales Manager | Admin |
|---|---|---|---|---|---|
| Browse products, cart | ✓ | ✓ | ✓ | ✓ | ✓ |
| Checkout, My orders (own only) | | ✓ | | | |
| Dashboard, record and update transactions | | | ✓ | ✓ | ✓ |
| Customers: view, add, edit | | | ✓ | ✓ | ✓ |
| Products: view | | | ✓ | ✓ | ✓ |
| Products: add or edit, change prices | | | | ✓ | ✓ |
| Delete transactions or customers | | | | ✓ | ✓ |
| Reports | | | | ✓ | ✓ |
| Employee accounts | | | | | ✓ |

This is enforced with decorators:

```python
@admin_bp.route("/reports")
@staff_required("manager")          # sales_exec gets 403 Forbidden
def reports(): ...
```

`ROLE_LEVEL = {"sales_exec": 1, "manager": 2, "admin": 3}`: a route requiring "manager" allows any level of 2 or above.

**Hiding a button is not security.** The sidebar hides Reports from Sales Executives for convenience, but the real protection is the decorator. Typing `/admin/reports` into the address bar still gives 403.

**Customer isolation:** every customer query includes the customer's own ID:

```sql
SELECT * FROM order_summary WHERE order_id = ? AND customer_id = ?
```

Alice typing `/account/orders/57` (Bob's order) gets 404, as if it didn't exist.

---

## 8. Security features

| Threat | What it is | Defence in this project |
|---|---|---|
| SQL injection | Typing SQL into a form so it runs on the database, e.g. `' OR 1=1 --` | Every value is a `?` parameter. Column names for sorting come from a fixed whitelist dictionary (`PRODUCT_SORTS`, `ORDER_SORTS`), never from user text |
| CSRF | Another website silently submitting a form to ours using your logged-in cookie | `CSRFProtect` requires a secret token in every POST form (`form.hidden_tag()` or `csrf_token()`); cookie is `SameSite=Lax` |
| XSS | Saving `<script>` in a field so it runs in someone else's browser | Jinja2 escapes all output automatically; chart data uses the `tojson` filter |
| Password theft | Reading passwords from a stolen database | Salted hashes only |
| Session tampering | Editing the cookie to become admin | Signed cookie, and the user is reloaded from the database each request |
| Open redirect | `?next=https://evil.com` after login | `safe_next()` only allows paths on our own site |
| Username discovery | Learning which emails are registered | Same "Invalid email or password" message for both mistakes |
| Secrets in code | SECRET_KEY visible in shared code | Read from `.env`, which is excluded in `.gitignore` |
| Logout via a link | A third-party page logging you out | Logout is a POST with a CSRF token |

---

## 9. The customer website

| Page | URL | Notes |
|---|---|---|
| Home | `/` | Hero, category tiles with live product counts, "Popular right now" from real sales data |
| Products | `/products` | **One card per product name (51 cards).** Search, category filter and sort, all in the URL so results can be bookmarked |
| Choose brand | `/item/<name>` | Every brand of that product, cheapest first, each with its own Add button |
| Product detail | `/products/<id>` | Price, MRP, % saved, shelf life from the category, stock status, related items |
| Cart | `/cart` | Stored in the session as product ID → quantity only. Prices are always re-read from the database. Works before login and is kept after login |
| Checkout | `/checkout` | Login required. Simulated UPI or card (marked paid) or cash on delivery (pending). Uses the same `create_order()` as staff |
| My orders | `/account/orders` | Only the logged-in customer's orders |
| Register / Login | `/register`, `/login` | Validation messages under each field |
| About, Contact | `/about`, `/contact` | Verified Blinkit facts with source. **Edit the project-team box in `templates/public/contact.html`** |

**Why the shop groups products.** The Excel file has 268 rows but only 51 product names: "Cheese" comes from 5 brands, "Pet Treats" from 12. Listing every row made the same name repeat many times. The products page now uses `GROUP BY p.name` (the `CATALOG_SELECT` query in `routes/public.py`), so each name appears once with "5 brands available · from ₹96". The `/item/<name>` page then lists the individual brands. Each brand is still its own row, with its own price and stock, and the cart and orders still use the exact brand (`product_id`). The staff Products page shows all 268 rows, because staff manage stock per brand. Queries C5a–C5c in `queries.sql` show this step by step.

The shop and the dashboard use separate stylesheets and layouts (`public.css` vs `admin.css`), so the two interfaces look visually distinct, as your brief requires.

---

## 10. Testing

### 10.1 Automated tests

```bash
python -m pytest -v
```

Expected result: `48 passed`. Each test runs against a fresh temporary copy of the database, so your real data is never touched.

| Group | What is tested |
|---|---|
| Public pages | All 10 pages load; unknown product gives 404; search works |
| SQL injection | `' OR 1=1 --` in search and `DROP TABLE` in sort do nothing harmful |
| Registration | Success with hashed password; duplicate email rejected; missing fields, bad phone and mismatched passwords all show errors and save nothing |
| Login failures | Wrong customer password; wrong staff password; deactivated employee |
| Access control | Visitor and customer are redirected from `/admin`; Sales Executive gets 403 on reports, employees, product edit and delete; manager gets 403 on employees; a customer can't open another customer's order; CSRF token required |
| Sales workflow | End-to-end save with server-calculated total (fake price ignored); duplicate rows merged; quantities 0, -2, abc and 5000 rejected; no products; no customer; future date; **insufficient stock rolls back everything** |
| After the sale | Cancel restores stock and refunds; delivered can't be reopened; delete restores stock; customer with orders can't be deleted; duplicate phone rejected; MRP below price rejected; price change doesn't alter old orders |
| Checkout | Guest cart, login required, cart kept, cash-on-delivery pending, stock reduced; can't add more than stock |
| Reports | Revenue shown equals a raw SQL SUM |

### 10.2 Manual testing checklist

Tick these off in the browser before your evaluation.

**Customer interface**
- [ ] Home page shows 11 categories and popular products
- [ ] Search "milk" shows only milk products; clearing the search shows all 268
- [ ] Category filter and each sort option work
- [ ] Add a product to the cart as a guest; the cart count goes up
- [ ] Checkout asks you to log in; after logging in the cart is still there
- [ ] Place an order; it appears in My orders with the correct total
- [ ] Register with an existing email: error shown, no account created
- [ ] Register with a 5-digit phone: error shown
- [ ] Wrong password: "Invalid email or password"
- [ ] Logged in as a customer, open `/admin`: you're sent to the staff login

**Staff interface**
- [ ] Log in as priya@blinkit.test: Reports and Employees are not in the sidebar
- [ ] Type `/admin/reports` manually: 403 page
- [ ] Record a transaction with two products: it shows on the detail page and the dashboard
- [ ] Check that stock went down on the Products page
- [ ] Try quantity 0: error, nothing saved
- [ ] Try a quantity larger than stock: "Not enough stock", nothing saved
- [ ] Try a future date: error
- [ ] Cancel the order: stock goes back up, payment becomes Refunded
- [ ] Filter transactions by status and date, search "BLK-000010", sort by total
- [ ] Log in as manager: Reports work, edit a product price, check that the old order still shows the old price
- [ ] Try to delete a customer who has orders: blocked with a message
- [ ] Log in as admin: create an employee, deactivate them, check they can't log in

### 10.3 Checking that records really are in the database

Install **[DB Browser for SQLite](https://sqlitebrowser.org/)** (free). Open `instance/blinkit.db`:

- **Browse Data** tab: choose `orders` and scroll to the bottom to see the transaction you just saved.
- **Execute SQL** tab: paste any query from `queries.sql` and press Run.

Or with Python, from the project folder:

```bash
python -c "import sqlite3; c=sqlite3.connect('instance/blinkit.db'); print(c.execute('SELECT * FROM order_summary ORDER BY order_id DESC LIMIT 3').fetchall())"
```

---

## 11. Troubleshooting

| Error or symptom | Cause | Fix |
|---|---|---|
| `'python' is not recognized` | Python not on PATH (Windows) | Reinstall with "Add Python to PATH" ticked, or use `py` instead of `python` |
| `ModuleNotFoundError: No module named 'flask'` | Packages not installed, or venv not active | Activate the venv (`(venv)` in the prompt), then `pip install -r requirements.txt` |
| Page says "The database has not been created yet" | `seed.py` not run | Stop the server, run `python seed.py`, start again |
| `FileNotFoundError: ... blinkit_dataset.xlsx` | Excel file moved or renamed | Put it at `data/blinkit_dataset.xlsx` |
| `UserWarning: SECRET_KEY not set` | No `.env` file | `copy .env.example .env` and set a value. It still runs without this, but the warning stays |
| "The form expired or was tampered with" (400) | CSRF token missing or old (e.g. after restarting with a new SECRET_KEY) | Refresh the page and submit again |
| `Address already in use` / port 5000 busy | Another program is on port 5000 (common on macOS: AirPlay Receiver) | `flask --app app run --port 5001`, then open http://127.0.0.1:5001 |
| `jinja2.exceptions.TemplateNotFound` | Template file renamed or in the wrong folder | Templates must be inside `templates/public/` or `templates/admin/` exactly as named in `render_template()` |
| `jinja2 ... UndefinedError: 'x' is undefined` | Template uses a variable the route didn't pass | Add it to the `render_template(...)` call |
| `sqlite3.IntegrityError: UNIQUE constraint failed` | Inserting a duplicate | Expected behaviour: the app catches these and shows a message |
| `sqlite3.IntegrityError: FOREIGN KEY constraint failed` | Referring to a row that doesn't exist, or deleting a parent that still has children | Check IDs. Deleting a customer with orders is blocked on purpose |
| `sqlite3.OperationalError: database is locked` | DB Browser has uncommitted changes open | In DB Browser click "Write Changes" or close the file |
| Charts don't appear | `static/js/chart.umd.min.js` missing | Restore that file from the project zip |
| Changes to HTML/CSS don't show | Browser cache | Hard refresh: `Ctrl + F5` (Windows) or `Cmd + Shift + R` (Mac) |

**Debug mode:** `python app.py` runs with `debug=True`. The server restarts when you save a file, and errors show a detailed page in the browser. Never use debug mode on a public server.

---

## 12. 5-minute demo script for your evaluation

Run `python seed.py` just before, so the data is fresh.

1. **(30 s) The problem.** "Sales staff need one system to record transactions and see reports, and customers need to browse and order. Both use the same database, with strict access control."
2. **(60 s) Customer site.** Home → search "chips" → open Chips → pick a brand → add to cart → log in as demo@example.com → checkout with UPI → My orders shows `BLK-000481`.
3. **(30 s) Access control.** While logged in as a customer, type `/admin` → redirected to staff login.
4. **(90 s) Sales workflow.** Log in as Priya → dashboard → New transaction → choose a customer, add 2 products (point out the live estimate) → Save → the transaction page shows the server-calculated total → back on the dashboard it's at the top of Recent transactions → Products page shows reduced stock.
5. **(30 s) Validation.** New transaction with quantity larger than stock → "Not enough stock", and nothing is saved, because the transaction rolled back.
6. **(30 s) Roles.** As Priya, type `/admin/reports` → 403. Log out, log in as manager → Reports with monthly chart, HAVING and NOT EXISTS sections.
7. **(30 s) Database.** Show `docs/erd.png`, then DB Browser with the new order rows in `orders`, `order_items` and `payments`.
8. **(Optional) Tests.** `python -m pytest -q` → `48 passed`.

---

## 13. Limitations and future enhancements

**Limitations (be honest about these in your report)**

- Customer and order records are synthetic. Blinkit's real transaction data is not public.
- The dataset's brand names and prices are illustrative (e.g. onions at ₹948), not Blinkit's real catalogue.
- Payments are simulated. There is no payment gateway.
- SQLite allows one writer at a time, which is fine for a demo but not for thousands of simultaneous users.
- There are no product photos, so emoji icons are used instead.
- There is no password reset or email verification.
- Money is stored as REAL (floating point) and rounded to 2 decimals. A production system would store whole paise as INTEGER, or use DECIMAL in MySQL, to avoid rounding errors.
- Staff-created customers have no online login.

**Future enhancements**

- Move to MySQL or PostgreSQL for multi-user production use.
- Integrate a payment gateway in test mode (e.g. Razorpay or Stripe sandbox).
- Multiple dark stores, with an inventory table per store.
- Automatic reorder alerts by email when stock falls below the minimum.
- Export reports to CSV or PDF.
- Password reset by email, and login rate-limiting.
- A REST API for a mobile app.
- Sales forecasting from order history.
- Delivery tracking with a delivery-partner role.

---

## 14. Viva questions and answers

**Architecture**

1. **What is your project?** A database-driven website for a quick-commerce company modelled on Blinkit. It has two interfaces, a customer shop and an internal sales dashboard, sharing one SQLite database through a Flask backend.
2. **Why Flask and not Django?** Flask is a micro-framework: it gives routing, templates and sessions, and I add only what I need. Writing my own SQL means I can explain every query. Django includes an ORM and admin panel that would hide much of the logic.
3. **What is a blueprint?** A group of related routes. I have `public_bp` for the shop and `admin_bp` for `/admin`, so each interface lives in its own file within one app.
4. **What is a route?** A mapping from a URL to a Python function, written with the `@bp.route("/path")` decorator.
5. **What is the difference between GET and POST?** GET requests data, and parameters appear in the URL (search filters). POST sends data that changes something (saving an order) in the request body, and it's protected by a CSRF token.
6. **What is Jinja2?** Flask's template engine. `{{ }}` prints a value, escaped for safety; `{% %}` runs logic like loops and if-statements; `{% extends %}` reuses a base layout.
7. **What is Post/Redirect/Get?** After a successful POST, the server redirects to a GET page. Refreshing then reloads that page instead of resubmitting the form, which prevents duplicate orders.

**Database and SQL**

8. **What are primary and foreign keys?** A primary key uniquely identifies each row (`order_id`). A foreign key is a column that must match a primary key in another table (`orders.customer_id` → `customers.customer_id`), which keeps references valid.
9. **Explain normalization with your project.** In the Excel file, margin and shelf life repeat for every product in a category: they depend on the category, not the product. That's a transitive dependency, so I moved them to a `categories` table. That's 3NF. Margin was also derivable as (mrp - price) / mrp.
10. **Explain each relationship type in your schema.** One-to-many: category→products, customer→orders. Many-to-many: orders↔products, through `order_items`. One-to-one: orders→payments, enforced by UNIQUE on `payments.order_id`.
11. **Why store unit_price in order_items when products already has price?** Prices change. The order must record what the customer actually paid, so old orders stay correct after a price change.
12. **What does ON DELETE CASCADE vs RESTRICT do?** CASCADE deletes the children automatically: deleting an order removes its items and payment. RESTRICT blocks the delete: a customer with orders can't be deleted, because sales history must be kept.
13. **What is a transaction? What are ACID properties?** A group of SQL statements that succeed or fail together. Atomicity (all or nothing), Consistency (constraints always hold), Isolation (concurrent transactions don't interfere), Durability (committed data survives a crash). My `create_order()` uses one transaction for order, items, payment and stock.
14. **WHERE vs HAVING?** WHERE filters rows before grouping; HAVING filters groups after aggregation. Example: `HAVING COUNT(*) >= 3` finds repeat customers.
15. **INNER JOIN vs LEFT JOIN?** INNER JOIN returns only matching rows. LEFT JOIN keeps every row from the left table even with no match, e.g. employees with zero sales still appear.
16. **Give an example of a subquery.** Orders above average: `WHERE total_amount > (SELECT AVG(total_amount) FROM orders)`. Products never sold: `WHERE NOT EXISTS (SELECT 1 FROM order_items ...)`.
17. **What is an index? Which did you create?** A data structure that speeds up lookups, like a book index. I created them on foreign keys and frequently filtered columns such as `orders(order_date)` and `orders(status)`. The trade-off is slightly slower inserts.
18. **What is a view?** A saved SELECT. `order_summary` joins four tables and is reused by several pages. It stores no data.
19. **Why SQLite?** Zero setup, a single file, and full SQL support. Its limitation is one writer at a time; production would use MySQL or PostgreSQL.
20. **How is the transaction ID generated?** `INTEGER PRIMARY KEY AUTOINCREMENT`. SQLite assigns the next number and never reuses one; Python reads it with `cursor.lastrowid`.

**Python and backend**

21. **How does Flask connect to SQLite?** `db.get_db()` opens a `sqlite3` connection per request, stores it on `g`, enables foreign keys, and closes it in a teardown function.
22. **How do you prevent SQL injection?** Parameterized queries: values are passed separately to `?` placeholders, so they're always treated as data, never as SQL. For ORDER BY, which can't use `?`, I map user choices to fixed strings from a whitelist.
23. **How is the order total calculated? Can the user change it?** In Python, from prices read from the database. The browser sends only product IDs and quantities, so extra fields like `price` are ignored. A test verifies this.
24. **What happens if one product is out of stock in a 3-product order?** The conditional UPDATE affects 0 rows, Python raises `OrderError`, and the transaction rolls back: no order, items or payment are saved, and stock is unchanged.
25. **How are forms validated?** Flask-WTF validators (DataRequired, Length, Regexp for phone and email, NumberRange, custom `validate_<field>` methods), plus database constraints as a second layer.

**Security and authentication**

26. **How are passwords stored?** As salted hashes using Werkzeug's `generate_password_hash`. Login uses `check_password_hash`. The plain password is never stored.
27. **What is CSRF and how do you prevent it?** Cross-Site Request Forgery is another site submitting a form using your logged-in cookie. Flask-WTF adds a secret token to each form and rejects POSTs without it.
28. **How do you stop a customer from opening the admin dashboard?** Every admin route has `@staff_required`, which checks that the session user is an active employee; customers are redirected to the staff login. Roles are checked with `ROLE_LEVEL`, and a lower role gets 403.
29. **How do you stop a customer seeing another customer's order?** The query includes `AND customer_id = ?` with the logged-in customer's ID, so another customer's order returns nothing and gives 404.
30. **What is the SECRET_KEY for?** Flask signs the session cookie with it so users can't tamper with it, and Flask-WTF uses it for CSRF tokens. It's kept in `.env`, not in the code.

**About the data**

31. **Is this real Blinkit data?** No. Products come from a public sample dataset modelled on Blinkit; the brand names and prices are illustrative. Customers and orders are synthetic, generated by `seed.py` and marked `is_sample = 1`. Only the company facts on the About page are real, and they're cited.

32. **Why does the shop show 51 products when the table has 268 rows?** The dataset has 51 product names, each sold by several brands. The shop query groups rows with `GROUP BY p.name` and uses `COUNT(*)` for the number of brands, `MIN(price)` for the "from" price and `SUM(stock_qty)` for total stock. The brand page then selects `WHERE name = ?`. Each brand stays a separate row, so stock and orders are tracked per brand.

---

## 15. About the data

- **Products:** `data/blinkit_dataset.xlsx`, the sample dataset you provided (268 products, 11 categories). The brand names are generated (e.g. "Aurora LLC") and the prices are illustrative.
- **Stock levels:** the dataset has min and max stock but not current stock, so `seed.py` generates current stock between 0 and the max. About 1 in 8 products starts at or below its reorder level, so the low-stock features have something to show.
- **Customers and orders:** synthetic, from a fixed random seed (42), so everyone gets identical data. Emails use `example.com`, a domain reserved for examples. Every generated row has `is_sample = 1` and is labelled "sample" in the dashboard.
- **Company facts** (About page): Wikipedia, "Blinkit", https://en.wikipedia.org/wiki/Blinkit, checked October 2026.
- **The site states clearly** that it is an academic project not affiliated with Blinkit or Eternal Ltd. Keep that banner.
