-- Historical SQL blocks; exact measured statements are preserved below.
-- These are benchmark inputs, not production reporting definitions.

-- benchmark-query: 01_monthly_revenue
-- Gross recorded revenue across all statuses; exclude soft-deleted orders.
SELECT date_trunc('month', order_date)::date AS month,
       count(*) AS total_orders, sum(total_amount) AS total_revenue
FROM "order"
WHERE NOT is_deleted
GROUP BY 1 ORDER BY 1;

-- benchmark-query: 02_orders_by_seller_and_date
-- Example: seller 1, March 2025. EXISTS avoids duplicating multi-item orders.
SELECT o.order_id, o.order_code, o.customer_id, o.order_date, o.status, o.total_amount
FROM "order" o
WHERE NOT o.is_deleted
  AND o.order_date >= TIMESTAMP '2025-03-01'
  AND o.order_date < TIMESTAMP '2025-04-01'
  AND EXISTS (
      SELECT 1 FROM order_item oi JOIN product p ON p.product_id = oi.product_id
      WHERE oi.order_id = o.order_id AND p.seller_id = 1
        AND NOT oi.is_deleted AND NOT p.is_deleted
  )
ORDER BY o.order_date, o.order_id;

-- benchmark-query: 03_items_by_product
-- Example product_id = 1. Export all matching rows, without a LIMIT.
SELECT order_item_id, order_item_code, order_id, product_id, order_date,
       quantity, unit_price, subtotal
FROM order_item
WHERE product_id = 1 AND NOT is_deleted
ORDER BY order_date, order_item_id;

-- benchmark-query: 04_highest_value_order
-- Deterministic tie-break: lowest order_id among equally valuable orders.
SELECT order_id, order_code, customer_id, order_date, status, total_amount
FROM "order" WHERE NOT is_deleted
ORDER BY total_amount DESC, order_id LIMIT 1;

-- benchmark-query: 05_top_products_by_quantity
-- Top 20 products by units sold across all recorded statuses.
SELECT p.product_id, p.product_code, p.product_name,
       sum(oi.quantity) AS total_quantity, sum(oi.subtotal) AS total_revenue
FROM order_item oi
JOIN product p ON p.product_id = oi.product_id
JOIN "order" o ON o.order_id = oi.order_id
WHERE NOT oi.is_deleted AND NOT p.is_deleted AND NOT o.is_deleted
GROUP BY p.product_id, p.product_code, p.product_name
ORDER BY total_quantity DESC, p.product_id LIMIT 20;

-- benchmark-query: 06_orders_by_seller_march_2025
-- Seller-level March summary; each seller counts each of their orders once.
-- Revenue is seller item revenue, not the full value of multi-seller orders.
SELECT s.seller_id, s.seller_code, s.seller_name,
       count(DISTINCT o.order_id) AS total_orders,
       sum(oi.quantity) AS total_quantity, sum(oi.subtotal) AS total_revenue
FROM seller s
JOIN product p ON p.seller_id = s.seller_id
JOIN order_item oi ON oi.product_id = p.product_id
JOIN "order" o ON o.order_id = oi.order_id
WHERE o.order_date >= TIMESTAMP '2025-03-01'
  AND o.order_date < TIMESTAMP '2025-04-01'
  AND NOT s.is_deleted AND NOT p.is_deleted
  AND NOT oi.is_deleted AND NOT o.is_deleted
GROUP BY s.seller_id, s.seller_code, s.seller_name ORDER BY s.seller_id;

-- benchmark-query: 07_product_monthly_revenue
SELECT date_trunc('month', o.order_date)::date AS month,
       p.product_id, p.product_code, p.product_name,
       sum(oi.quantity) AS total_quantity, sum(oi.subtotal) AS total_revenue
FROM order_item oi
JOIN product p ON p.product_id = oi.product_id
JOIN "order" o ON o.order_id = oi.order_id
WHERE NOT oi.is_deleted AND NOT p.is_deleted AND NOT o.is_deleted
GROUP BY 1, p.product_id, p.product_code, p.product_name
ORDER BY month, p.product_id;

-- benchmark-query: 08_products_sold_per_seller
-- Distinguish distinct product types, item rows, orders, and units sold.
SELECT s.seller_id, s.seller_code, s.seller_name,
       count(DISTINCT p.product_id) AS distinct_products_sold,
       count(DISTINCT o.order_id) AS total_orders,
       count(*) AS total_item_rows, sum(oi.quantity) AS total_quantity,
       sum(oi.subtotal) AS total_revenue
FROM seller s
JOIN product p ON p.seller_id = s.seller_id
JOIN order_item oi ON oi.product_id = p.product_id
JOIN "order" o ON o.order_id = oi.order_id
WHERE NOT s.is_deleted AND NOT p.is_deleted
  AND NOT oi.is_deleted AND NOT o.is_deleted
GROUP BY s.seller_id, s.seller_code, s.seller_name
ORDER BY total_quantity DESC, s.seller_id;
