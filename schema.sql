-- =====================================================================
-- schema.sql  -  Blinkit Sales Portal (academic project)
-- Database: SQLite 3
--
-- Run automatically by:  python seed.py
-- Or manually:           sqlite3 instance/blinkit.db < schema.sql
--
-- Design notes (see PROJECT_GUIDE.md, section 3):
--   * 7 tables, normalised to Third Normal Form (3NF).
--   * margin % and shelf life depend on the CATEGORY, not the product,
--     so they live in `categories` (removes a transitive dependency).
--   * order_items.unit_price is the price AT THE TIME OF SALE, so old
--     orders do not change when a manager edits a product's price.
-- =====================================================================

PRAGMA foreign_keys = ON;

-- Drop in reverse dependency order so foreign keys don't block us.
DROP VIEW  IF EXISTS order_summary;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS employees;

-- ---------------------------------------------------------------------
-- 1. categories  (11 rows, from the Excel "category" column)
-- ---------------------------------------------------------------------
CREATE TABLE categories (
    category_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT    NOT NULL UNIQUE,
    standard_margin_pct INTEGER NOT NULL CHECK (standard_margin_pct BETWEEN 0 AND 100),
    shelf_life_days    INTEGER NOT NULL CHECK (shelf_life_days > 0)
);

-- ---------------------------------------------------------------------
-- 2. products  (268 rows, from the Excel sheet)
--    product_id keeps the ID from the dataset, so it is not AUTOINCREMENT.
-- ---------------------------------------------------------------------
CREATE TABLE products (
    product_id   INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL,
    brand        TEXT    NOT NULL,
    category_id  INTEGER NOT NULL REFERENCES categories(category_id) ON DELETE RESTRICT,
    price        REAL    NOT NULL CHECK (price > 0),          -- selling price (Rs)
    mrp          REAL    NOT NULL CHECK (mrp >= price),       -- printed MRP (Rs)
    stock_qty    INTEGER NOT NULL DEFAULT 0 CHECK (stock_qty >= 0),
    min_stock    INTEGER NOT NULL DEFAULT 0 CHECK (min_stock >= 0),
    max_stock    INTEGER NOT NULL CHECK (max_stock >= min_stock),
    is_active    INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    UNIQUE (name, brand)                                      -- no duplicate products
);

-- ---------------------------------------------------------------------
-- 3. customers
--    password_hash may be NULL: a customer created by sales staff over the
--    phone has no online login yet.
-- ---------------------------------------------------------------------
CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT    NOT NULL CHECK (length(trim(full_name)) >= 2),
    email         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    phone         TEXT    NOT NULL UNIQUE CHECK (length(phone) = 10),
    password_hash TEXT,
    address       TEXT    NOT NULL,
    city          TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    is_sample     INTEGER NOT NULL DEFAULT 0 CHECK (is_sample IN (0, 1))  -- 1 = synthetic demo row
);

-- ---------------------------------------------------------------------
-- 4. employees  (internal users)
--    Role is a CHECK-constrained column rather than a separate roles table:
--    there are only 3 fixed roles, so a lookup table would add a join and
--    nothing else.
-- ---------------------------------------------------------------------
CREATE TABLE employees (
    employee_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK (role IN ('sales_exec', 'manager', 'admin')),
    is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ---------------------------------------------------------------------
-- 5. orders  (one row per sales transaction)
--    order_id is the transaction ID; SQLite generates it (AUTOINCREMENT
--    never reuses an ID, even after a delete).
--    channel 'online' = placed by a customer on the website (no employee)
--    channel 'staff'  = recorded by a sales employee (employee required)
-- ---------------------------------------------------------------------
CREATE TABLE orders (
    order_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id  INTEGER NOT NULL REFERENCES customers(customer_id) ON DELETE RESTRICT,
    employee_id  INTEGER          REFERENCES employees(employee_id) ON DELETE RESTRICT,
    channel      TEXT    NOT NULL CHECK (channel IN ('online', 'staff')),
    order_date   TEXT    NOT NULL,                     -- 'YYYY-MM-DD HH:MM:SS'
    status       TEXT    NOT NULL DEFAULT 'placed'
                         CHECK (status IN ('placed', 'delivered', 'cancelled')),
    total_amount REAL    NOT NULL CHECK (total_amount >= 0),  -- calculated by the server
    notes        TEXT,
    is_sample    INTEGER NOT NULL DEFAULT 0 CHECK (is_sample IN (0, 1)),
    created_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    CHECK ( (channel = 'online' AND employee_id IS NULL)
         OR (channel = 'staff'  AND employee_id IS NOT NULL) )
);

-- ---------------------------------------------------------------------
-- 6. order_items  (resolves the MANY-TO-MANY between orders and products)
--    Composite primary key: the same product cannot appear twice in one
--    order (quantities are merged instead).
-- ---------------------------------------------------------------------
CREATE TABLE order_items (
    order_id    INTEGER NOT NULL REFERENCES orders(order_id)   ON DELETE CASCADE,
    product_id  INTEGER NOT NULL REFERENCES products(product_id) ON DELETE RESTRICT,
    quantity    INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 1000),
    unit_price  REAL    NOT NULL CHECK (unit_price > 0),       -- price at time of sale
    PRIMARY KEY (order_id, product_id)
);

-- ---------------------------------------------------------------------
-- 7. payments  (ONE-TO-ONE with orders: order_id is UNIQUE)
--    Simulated only. No real card or UPI details are ever stored.
-- ---------------------------------------------------------------------
CREATE TABLE payments (
    payment_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    INTEGER NOT NULL UNIQUE REFERENCES orders(order_id) ON DELETE CASCADE,
    method      TEXT    NOT NULL CHECK (method IN ('upi', 'card', 'cash', 'cod')),
    status      TEXT    NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'paid', 'failed', 'refunded')),
    amount      REAL    NOT NULL CHECK (amount >= 0),
    paid_at     TEXT
);

-- ---------------------------------------------------------------------
-- Indexes on columns we search, filter, join or sort by often.
-- (Primary keys and UNIQUE columns are indexed automatically.)
-- ---------------------------------------------------------------------
CREATE INDEX idx_products_category  ON products(category_id);
CREATE INDEX idx_products_name      ON products(name);
CREATE INDEX idx_orders_customer    ON orders(customer_id);
CREATE INDEX idx_orders_employee    ON orders(employee_id);
CREATE INDEX idx_orders_date        ON orders(order_date);
CREATE INDEX idx_orders_status      ON orders(status);
CREATE INDEX idx_order_items_product ON order_items(product_id);
CREATE INDEX idx_customers_name     ON customers(full_name);

-- ---------------------------------------------------------------------
-- A VIEW is a saved SELECT. The order list pages read from it so the
-- join logic is written once.
-- ---------------------------------------------------------------------
CREATE VIEW order_summary AS
SELECT  o.order_id,
        o.order_date,
        o.status,
        o.channel,
        o.total_amount,
        o.is_sample,
        o.customer_id,
        c.full_name          AS customer_name,
        o.employee_id,
        e.full_name          AS employee_name,
        p.method             AS payment_method,
        p.status             AS payment_status,
        (SELECT COUNT(*) FROM order_items oi WHERE oi.order_id = o.order_id) AS item_count
FROM    orders o
JOIN    customers c      ON c.customer_id = o.customer_id
LEFT JOIN employees e    ON e.employee_id = o.employee_id
LEFT JOIN payments  p    ON p.order_id    = o.order_id;
