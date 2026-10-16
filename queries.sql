-- =====================================================================
-- queries.sql  -  SQL practice queries (Phase 5: test SQL on its own)
--
-- Run AFTER `python seed.py`, from the project folder, in one of these ways:
--   * DB Browser for SQLite: open instance/blinkit.db -> "Execute SQL" tab
--     -> paste a query -> Run   (easiest, recommended)
--   * sqlite3 command line:  sqlite3 instance/blinkit.db < queries.sql
--
-- The INSERT / UPDATE / DELETE examples are wrapped in BEGIN ... ROLLBACK,
-- so they are undone at the end and your demo data stays unchanged.
-- =====================================================================
.headers on
.mode column
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- A. Basic SELECT
-- ---------------------------------------------------------------------
-- A1. All categories with their standard margin and shelf life
SELECT category_id, name, standard_margin_pct, shelf_life_days
FROM categories
ORDER BY name;

-- A2. The 5 most expensive products
SELECT product_id, name, brand, price, mrp
FROM products
ORDER BY price DESC
LIMIT 5;

-- A3. Products that need reordering (stock at or below the minimum)
SELECT product_id, name, brand, stock_qty, min_stock
FROM products
WHERE stock_qty <= min_stock
ORDER BY stock_qty;

-- A4. Search (what the website's search box runs). % is a wildcard.
SELECT product_id, name, brand, price
FROM products
WHERE name LIKE '%milk%' OR brand LIKE '%milk%';

-- ---------------------------------------------------------------------
-- B. JOIN queries (combining tables)
-- ---------------------------------------------------------------------
-- B1. INNER JOIN: every product with its category name
SELECT p.product_id, p.name, p.brand, c.name AS category, p.price
FROM products p
JOIN categories c ON c.category_id = p.category_id
ORDER BY c.name, p.name
LIMIT 10;

-- B2. Three-table JOIN: one order with its customer and payment
SELECT o.order_id, o.order_date, c.full_name AS customer,
       o.total_amount, pay.method, pay.status AS payment_status
FROM orders o
JOIN customers c  ON c.customer_id = o.customer_id
JOIN payments pay ON pay.order_id  = o.order_id
WHERE o.order_id = 1;

-- B3. Four-table JOIN: line items of order 1 with product and category
SELECT oi.order_id, p.name, p.brand, c.name AS category,
       oi.quantity, oi.unit_price,
       ROUND(oi.quantity * oi.unit_price, 2) AS line_total
FROM order_items oi
JOIN products p   ON p.product_id  = oi.product_id
JOIN categories c ON c.category_id = p.category_id
WHERE oi.order_id = 1;

-- B4. LEFT JOIN: every employee, including those with no sales
--     (online orders have employee_id NULL, so they are not counted here)
SELECT e.full_name, e.role, COUNT(o.order_id) AS orders_recorded
FROM employees e
LEFT JOIN orders o ON o.employee_id = e.employee_id
GROUP BY e.employee_id
ORDER BY orders_recorded DESC;

-- B5. The saved VIEW used by the website's transaction list
SELECT order_id, order_date, customer_name, employee_name, total_amount, status, payment_status
FROM order_summary
ORDER BY order_date DESC
LIMIT 5;

-- ---------------------------------------------------------------------
-- C. Business metrics with aggregate functions
-- ---------------------------------------------------------------------
-- C1. Headline numbers (cancelled orders excluded)
SELECT COUNT(*)                    AS total_orders,
       ROUND(SUM(total_amount), 2) AS total_revenue,
       ROUND(AVG(total_amount), 2) AS avg_order_value,
       ROUND(MAX(total_amount), 2) AS biggest_order,
       ROUND(MIN(total_amount), 2) AS smallest_order
FROM orders
WHERE status != 'cancelled';

-- C2. Revenue by category (GROUP BY)
SELECT c.name AS category,
       SUM(oi.quantity)                        AS units_sold,
       ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
FROM order_items oi
JOIN orders o     ON o.order_id    = oi.order_id
JOIN products p   ON p.product_id  = oi.product_id
JOIN categories c ON c.category_id = p.category_id
WHERE o.status != 'cancelled'
GROUP BY c.category_id
ORDER BY revenue DESC;

-- C3. Monthly revenue trend
SELECT strftime('%Y-%m', order_date) AS month,
       COUNT(*)                      AS orders,
       ROUND(SUM(total_amount), 2)   AS revenue
FROM orders
WHERE status != 'cancelled'
GROUP BY month
ORDER BY month;

-- C4. Orders by status and payment method
SELECT o.status, pay.method, COUNT(*) AS orders
FROM orders o JOIN payments pay ON pay.order_id = o.order_id
GROUP BY o.status, pay.method
ORDER BY o.status, orders DESC;

-- C5a. Why names repeat: 268 rows but only 51 product names
SELECT COUNT(*) AS total_rows, COUNT(DISTINCT name) AS distinct_names FROM products;

-- C5b. The shop page query: ONE row per product name (GROUP BY collapses the brands)
SELECT p.name, c.name AS category,
       COUNT(*)         AS brand_count,
       MIN(p.price)     AS cheapest_price,
       MAX(p.price)     AS dearest_price,
       SUM(p.stock_qty) AS total_stock
FROM products p
JOIN categories c ON c.category_id = p.category_id
WHERE p.is_active = 1
GROUP BY p.name, c.category_id
ORDER BY brand_count DESC;

-- C5c. Every brand of one product (the /item/Cheese page)
SELECT brand, price, mrp, stock_qty FROM products WHERE name = 'Cheese' ORDER BY price;

-- C5. Top 5 customers by spend
SELECT c.full_name, c.city, COUNT(*) AS orders, ROUND(SUM(o.total_amount), 2) AS spent
FROM orders o JOIN customers c ON c.customer_id = o.customer_id
WHERE o.status != 'cancelled'
GROUP BY c.customer_id
ORDER BY spent DESC
LIMIT 5;

-- ---------------------------------------------------------------------
-- D. HAVING and subqueries
-- ---------------------------------------------------------------------
-- D1. HAVING: categories that earned more than Rs 1,00,000
--     (WHERE filters rows BEFORE grouping, HAVING filters groups AFTER)
SELECT c.name AS category, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
FROM order_items oi
JOIN orders o     ON o.order_id    = oi.order_id
JOIN products p   ON p.product_id  = oi.product_id
JOIN categories c ON c.category_id = p.category_id
WHERE o.status != 'cancelled'
GROUP BY c.category_id
HAVING SUM(oi.quantity * oi.unit_price) > 100000
ORDER BY revenue DESC;

-- D2. HAVING: repeat customers with 10 or more orders
SELECT c.full_name, COUNT(*) AS orders
FROM orders o JOIN customers c ON c.customer_id = o.customer_id
GROUP BY c.customer_id
HAVING COUNT(*) >= 10
ORDER BY orders DESC;

-- D3. Subquery in WHERE: orders bigger than the average order
SELECT order_id, total_amount
FROM orders
WHERE total_amount > (SELECT AVG(total_amount) FROM orders)
ORDER BY total_amount DESC
LIMIT 10;

-- D4. NOT EXISTS: products that have never been sold
SELECT p.product_id, p.name, p.brand
FROM products p
WHERE NOT EXISTS (SELECT 1 FROM order_items oi WHERE oi.product_id = p.product_id);

-- D5. Subquery in FROM: each category's share of total revenue (%)
SELECT category, revenue,
       ROUND(100.0 * revenue / (SELECT SUM(quantity * unit_price) FROM order_items), 1) AS share_pct
FROM (SELECT c.name AS category, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
      FROM order_items oi
      JOIN products p   ON p.product_id  = oi.product_id
      JOIN categories c ON c.category_id = p.category_id
      GROUP BY c.category_id)
ORDER BY revenue DESC;

-- D6. Proof that margin_percentage was derivable: (mrp - price) / mrp
SELECT p.name, p.price, p.mrp,
       ROUND((p.mrp - p.price) / p.mrp * 100) AS calculated_margin,
       c.standard_margin_pct
FROM products p JOIN categories c ON c.category_id = p.category_id
LIMIT 5;

-- ---------------------------------------------------------------------
-- E. INSERT, UPDATE, DELETE (inside a transaction that is rolled back)
-- ---------------------------------------------------------------------
BEGIN TRANSACTION;

-- E1. INSERT a customer (customer_id is generated automatically)
INSERT INTO customers (full_name, email, phone, address, city)
VALUES ('Test Walk-in', 'walkin@example.com', '9000011111', 'Shop counter', 'Pune');
SELECT last_insert_rowid() AS new_customer_id;

-- E2. INSERT a complete order: order -> items -> payment -> stock
INSERT INTO orders (customer_id, employee_id, channel, order_date, total_amount)
VALUES (last_insert_rowid(), 3, 'staff', datetime('now', 'localtime'), 0);
INSERT INTO order_items (order_id, product_id, quantity, unit_price)
SELECT last_insert_rowid(), product_id, 2, price FROM products WHERE product_id = 153019;
UPDATE orders SET total_amount = (SELECT SUM(quantity * unit_price) FROM order_items
                                  WHERE order_id = orders.order_id)
WHERE order_id = (SELECT MAX(order_id) FROM orders);
INSERT INTO payments (order_id, method, status, amount)
SELECT order_id, 'cash', 'paid', total_amount FROM orders WHERE order_id = (SELECT MAX(order_id) FROM orders);
UPDATE products SET stock_qty = stock_qty - 2 WHERE product_id = 153019 AND stock_qty >= 2;
SELECT * FROM order_summary WHERE order_id = (SELECT MAX(order_id) FROM orders);

-- E3. UPDATE: mark that order delivered
UPDATE orders SET status = 'delivered' WHERE order_id = (SELECT MAX(order_id) FROM orders);

-- E4. UPDATE: 10% price cut on all Snacks (price must stay > 0, MRP >= price)
UPDATE products SET price = ROUND(price * 0.9, 2)
WHERE category_id = (SELECT category_id FROM categories WHERE name = 'Snacks & Munchies');

-- E5. DELETE: removing the order also removes its items and payment (ON DELETE CASCADE)
DELETE FROM orders WHERE order_id = (SELECT MAX(order_id) FROM orders);

-- E6. Constraints in action - each of these FAILS on purpose (uncomment to try):
-- INSERT INTO products (name, brand, category_id, price, mrp, max_stock) VALUES ('X', 'Y', 1, 100, 90, 10);
--     -> CHECK constraint failed: mrp >= price
-- INSERT INTO customers (full_name, email, phone, address, city) VALUES ('A', 'demo@example.com', '9000000099', 'x', 'y');
--     -> UNIQUE constraint failed: customers.email
-- DELETE FROM customers WHERE customer_id = 1;
--     -> FOREIGN KEY constraint failed (customer 1 has orders)
-- INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (1, 999999, 1, 10);
--     -> FOREIGN KEY constraint failed (no such product)

ROLLBACK;   -- undo everything in section E

-- After the rollback the test customer is gone again:
SELECT COUNT(*) AS should_be_zero FROM customers WHERE email = 'walkin@example.com';
