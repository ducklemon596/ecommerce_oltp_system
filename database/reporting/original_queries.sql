-- Authentic historical baselines recovered from Git commit fc35293.
-- Sources: benchmarks/original_queries.sql and benchmarks/dynamic_original.sql.
-- No optimized SQL is included. SELECT bodies retain historical join/aggregation logic.
-- Dynamic function bodies are rendered as direct SELECTs with explicit sample literals.
-- Original all-history analytical queries remain unbounded; compare with optimized
-- functions using DATE '-infinity' / DATE 'infinity', not a narrower window.
-- Seller/date example remains seller 1 in March; item export remains product 1.
-- The two seller-summary requirements share report_seller_sales; the March summary
-- is a date-window/projection use of that report, not a duplicate baseline below.
-- WARNING: original dynamic revenue reports use parent order timestamps; several
-- current functions use item timestamps. Dataset equivalence must be verified
-- before timing; equality of these dates is not guaranteed by the database schema.

-- ==============================================================================
-- ORIGINAL REPORT 01 | report_monthly_revenue
-- Function: report_monthly_revenue
-- Source: dynamic_original.sql / report_monthly_revenue
-- Parameters:
--   p_start_date = DATE '2025-01-01'
--   p_end_date = DATE '2025-06-01'
SELECT date_trunc('month', o.order_date)::DATE AS month,
           count(DISTINCT o.order_id) AS total_orders,
           sum(oi.quantity)::BIGINT AS total_quantity,
           sum(oi.subtotal) AS total_revenue
    FROM "order" AS o
    JOIN order_item AS oi ON oi.order_id = o.order_id
    WHERE o.order_date >= DATE '2025-01-01'::TIMESTAMP
      AND o.order_date < DATE '2025-06-01'::TIMESTAMP
      AND NOT o.is_deleted
      AND NOT oi.is_deleted
    GROUP BY 1
    ORDER BY 1;
-- END ORIGINAL REPORT 01

-- ==============================================================================
-- ORIGINAL REPORT 02 | report_daily_revenue
-- Function: report_daily_revenue
-- Source: dynamic_original.sql / report_daily_revenue
-- Parameters:
--   p_start_date = DATE '2025-01-01'
--   p_end_date = DATE '2025-06-01'
--   p_product_ids = ARRAY[1, 2]::INTEGER[]
SELECT o.order_date::DATE AS date,
           count(DISTINCT o.order_id) AS total_orders,
           sum(oi.quantity)::BIGINT AS total_quantity,
           sum(oi.subtotal) AS total_revenue
    FROM "order" AS o
    JOIN order_item AS oi ON oi.order_id = o.order_id
    WHERE o.order_date >= DATE '2025-01-01'::TIMESTAMP
      AND o.order_date < DATE '2025-06-01'::TIMESTAMP
      AND (ARRAY[1, 2]::INTEGER[] IS NULL OR oi.product_id = ANY (ARRAY[1, 2]::INTEGER[]))
      AND NOT o.is_deleted
      AND NOT oi.is_deleted
    GROUP BY 1
    ORDER BY 1;
-- END ORIGINAL REPORT 02

-- ==============================================================================
-- ORIGINAL REPORT 03 | report_seller_performance
-- Function: report_seller_performance
-- Source: dynamic_original.sql / report_seller_performance
-- Parameters:
--   p_start_date = DATE '2025-01-01'
--   p_end_date = DATE '2025-06-01'
--   p_category_ids = ARRAY[6, 7]::INTEGER[]
--   p_brand_ids = ARRAY[1, 2]::INTEGER[]
SELECT s.seller_id,
           s.seller_name,
           count(DISTINCT o.order_id) AS total_orders,
           sum(oi.quantity)::BIGINT AS total_quantity,
           sum(oi.subtotal) AS total_revenue
    FROM order_item AS oi
    JOIN "order" AS o ON o.order_id = oi.order_id
    JOIN product AS p ON p.product_id = oi.product_id
    JOIN seller AS s ON s.seller_id = p.seller_id
    WHERE o.order_date >= DATE '2025-01-01'::TIMESTAMP
      AND o.order_date < DATE '2025-06-01'::TIMESTAMP
      AND (ARRAY[6, 7]::INTEGER[] IS NULL OR p.category_id = ANY (ARRAY[6, 7]::INTEGER[]))
      AND (ARRAY[1, 2]::INTEGER[] IS NULL OR p.brand_id = ANY (ARRAY[1, 2]::INTEGER[]))
      AND NOT o.is_deleted
      AND NOT oi.is_deleted
      AND NOT p.is_deleted
      AND NOT s.is_deleted
    GROUP BY s.seller_id, s.seller_name
    ORDER BY s.seller_id;
-- END ORIGINAL REPORT 03

-- ==============================================================================
-- ORIGINAL REPORT 04 | report_top_products_per_brand
-- Function: report_top_products_per_brand
-- Source: dynamic_original.sql / report_top_products_per_brand
-- Parameters:
--   p_start_date = DATE '2025-01-01'
--   p_end_date = DATE '2025-06-01'
--   p_seller_ids = ARRAY[1, 2]::INTEGER[]
--   p_top_n = 5
WITH product_sales AS (
        SELECT b.brand_id,
               b.brand_name,
               p.product_id,
               p.product_name,
               sum(oi.quantity)::BIGINT AS total_quantity,
               sum(oi.subtotal) AS total_revenue
        FROM order_item AS oi
        JOIN "order" AS o ON o.order_id = oi.order_id
        JOIN product AS p ON p.product_id = oi.product_id
        JOIN brand AS b ON b.brand_id = p.brand_id
        WHERE o.order_date >= DATE '2025-01-01'::TIMESTAMP
          AND o.order_date < DATE '2025-06-01'::TIMESTAMP
          AND (ARRAY[1, 2]::INTEGER[] IS NULL OR p.seller_id = ANY (ARRAY[1, 2]::INTEGER[]))
          AND NOT o.is_deleted
          AND NOT oi.is_deleted
          AND NOT p.is_deleted
          AND NOT b.is_deleted
        GROUP BY b.brand_id, b.brand_name, p.product_id, p.product_name
    ), ranked_products AS (
        SELECT ps.*,
               row_number() OVER (
                   PARTITION BY ps.brand_id
                   ORDER BY ps.total_quantity DESC, ps.total_revenue DESC, ps.product_id
               ) AS brand_rank
        FROM product_sales AS ps
    )
    SELECT rp.brand_id, rp.brand_name, rp.product_id, rp.product_name,
           rp.total_quantity, rp.total_revenue
    FROM ranked_products AS rp
    WHERE rp.brand_rank <= greatest(5, 0)
    ORDER BY rp.brand_id, rp.brand_rank;
-- END ORIGINAL REPORT 04

-- ==============================================================================
-- ORIGINAL REPORT 05 | report_order_status_summary
-- Function: report_order_status_summary
-- Source: dynamic_original.sql / report_order_status_summary
-- Parameters:
--   p_start_date = DATE '2025-01-01'
--   p_end_date = DATE '2025-06-01'
--   p_seller_ids = ARRAY[1, 2]::INTEGER[]
--   p_category_ids = ARRAY[6, 7]::INTEGER[]
SELECT o.status,
           count(*) AS total_orders,
           sum(o.total_amount) AS total_revenue
    FROM "order" AS o
    WHERE o.order_date >= DATE '2025-01-01'::TIMESTAMP
      AND o.order_date < DATE '2025-06-01'::TIMESTAMP
      AND NOT o.is_deleted
      AND (
          (ARRAY[1, 2]::INTEGER[] IS NULL AND ARRAY[6, 7]::INTEGER[] IS NULL)
          OR EXISTS (
              SELECT 1
              FROM order_item AS oi
              JOIN product AS p ON p.product_id = oi.product_id
              WHERE oi.order_id = o.order_id
                AND NOT oi.is_deleted
                AND NOT p.is_deleted
                AND (ARRAY[1, 2]::INTEGER[] IS NULL OR p.seller_id = ANY (ARRAY[1, 2]::INTEGER[]))
                AND (ARRAY[6, 7]::INTEGER[] IS NULL OR p.category_id = ANY (ARRAY[6, 7]::INTEGER[]))
          )
      )
    GROUP BY o.status
    ORDER BY o.status;
-- END ORIGINAL REPORT 05

-- ==============================================================================
-- ORIGINAL REPORT 06 | report_monthly_order_revenue
-- Function: report_monthly_order_revenue
-- Source: original_queries.sql / 01_monthly_revenue
-- Gross recorded revenue across all statuses; exclude soft-deleted orders.
SELECT date_trunc('month', order_date)::date AS month,
       count(*) AS total_orders, sum(total_amount) AS total_revenue
FROM "order"
WHERE NOT is_deleted
GROUP BY 1 ORDER BY 1;
-- END ORIGINAL REPORT 06

-- ==============================================================================
-- ORIGINAL REPORT 07 | report_orders_by_seller
-- Function: report_orders_by_seller
-- Source: original_queries.sql / 02_orders_by_seller_and_date
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
-- END ORIGINAL REPORT 07

-- ==============================================================================
-- ORIGINAL REPORT 08 | report_items_by_product
-- Function: report_items_by_product
-- Source: original_queries.sql / 03_items_by_product
-- Example product_id = 1. Export all matching rows, without a LIMIT.
SELECT order_item_id, order_item_code, order_id, product_id, order_date,
       quantity, unit_price, subtotal
FROM order_item
WHERE product_id = 1 AND NOT is_deleted
ORDER BY order_date, order_item_id;
-- END ORIGINAL REPORT 08

-- ==============================================================================
-- ORIGINAL REPORT 09 | report_highest_value_orders
-- Function: report_highest_value_orders
-- Source: original_queries.sql / 04_highest_value_order
-- Deterministic tie-break: lowest order_id among equally valuable orders.
SELECT order_id, order_code, customer_id, order_date, status, total_amount
FROM "order" WHERE NOT is_deleted
ORDER BY total_amount DESC, order_id LIMIT 1;
-- END ORIGINAL REPORT 09

-- ==============================================================================
-- ORIGINAL REPORT 10 | report_top_products
-- Function: report_top_products
-- Source: original_queries.sql / 05_top_products_by_quantity
-- Top 20 products by units sold across all recorded statuses.
SELECT p.product_id, p.product_code, p.product_name,
       sum(oi.quantity) AS total_quantity, sum(oi.subtotal) AS total_revenue
FROM order_item oi
JOIN product p ON p.product_id = oi.product_id
JOIN "order" o ON o.order_id = oi.order_id
WHERE NOT oi.is_deleted AND NOT p.is_deleted AND NOT o.is_deleted
GROUP BY p.product_id, p.product_code, p.product_name
ORDER BY total_quantity DESC, p.product_id LIMIT 20;
-- END ORIGINAL REPORT 10

-- ==============================================================================
-- ORIGINAL REPORT 11 | report_seller_sales
-- Function: report_seller_sales
-- Source: original_queries.sql / 08_products_sold_per_seller
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
-- END ORIGINAL REPORT 11

-- ==============================================================================
-- ORIGINAL REPORT 12 | report_product_monthly_revenue
-- Function: report_product_monthly_revenue
-- Source: original_queries.sql / 07_product_monthly_revenue
SELECT date_trunc('month', o.order_date)::date AS month,
       p.product_id, p.product_code, p.product_name,
       sum(oi.quantity) AS total_quantity, sum(oi.subtotal) AS total_revenue
FROM order_item oi
JOIN product p ON p.product_id = oi.product_id
JOIN "order" o ON o.order_id = oi.order_id
WHERE NOT oi.is_deleted AND NOT p.is_deleted AND NOT o.is_deleted
GROUP BY 1, p.product_id, p.product_code, p.product_name
ORDER BY month, p.product_id;
-- END ORIGINAL REPORT 12
