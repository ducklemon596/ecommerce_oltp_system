-- Standalone optimized reporting queries with explicit sample values.
-- Select one complete statement in pgAdmin; prefix it with EXPLAIN (ANALYZE, BUFFERS)
-- to inspect its plan. Windows include start_date and exclude end_date.
-- Dates cover Jan-May 2025; lists use IDs 1 and 2. Edit the literals for your workload.
-- functions.sql retains the parameterized interfaces; these SELECTs specialize their filters.

-- Each numbered REPORT/END REPORT block is one independently executable statement.

-- ==============================================================================
-- REPORT 01 | MONTHLY ITEM REVENUE
-- Function: report_monthly_revenue
-- Item-date window; active-item subtotals, not full order totals.
-- Literal values:
--   Start date: DATE '2025-01-01'
--   End date: DATE '2025-06-01'
-- ==============================================================================
SELECT
    DATE_TRUNC('month', oi.order_date)::DATE AS month,
    COUNT(DISTINCT oi.order_id) AS total_orders,
    SUM(oi.quantity)::BIGINT AS total_quantity,
    SUM(oi.subtotal) AS total_revenue
FROM order_item oi
WHERE oi.order_date >= DATE '2025-01-01'::TIMESTAMP
  AND oi.order_date < DATE '2025-06-01'::TIMESTAMP
  AND NOT oi.is_deleted
  AND NOT EXISTS (
      SELECT 1
      FROM "order" o
      WHERE o.order_id = oi.order_id
        AND o.is_deleted
  )
GROUP BY 1
ORDER BY 1;
-- END REPORT 01 | report_monthly_revenue

-- ==============================================================================
-- REPORT 02 | DAILY ITEM REVENUE
-- Function: report_daily_revenue
-- Item-date window; only matching product subtotals contribute.
-- Literal values:
--   Start date: DATE '2025-01-01'
--   End date: DATE '2025-06-01'
--   Product IDs: (1, 2)
-- ==============================================================================
SELECT
    oi.order_date::DATE AS date,
    COUNT(DISTINCT oi.order_id) AS total_orders,
    SUM(oi.quantity)::BIGINT AS total_quantity,
    SUM(oi.subtotal) AS total_revenue
FROM order_item oi
WHERE oi.order_date >= DATE '2025-01-01'::TIMESTAMP
  AND oi.order_date < DATE '2025-06-01'::TIMESTAMP
  AND oi.product_id IN (1, 2)
  AND NOT oi.is_deleted
  AND NOT EXISTS (
      SELECT 1
      FROM "order" o
      WHERE o.order_id = oi.order_id
        AND o.is_deleted
  )
GROUP BY 1
ORDER BY 1;
-- END REPORT 02 | report_daily_revenue

-- ==============================================================================
-- REPORT 03 | SELLER PERFORMANCE
-- Function: report_seller_performance
-- Item-date window; category/brand filters apply before seller aggregation.
-- Literal values:
--   Start date: DATE '2025-01-01'
--   End date: DATE '2025-06-01'
--   Category IDs: (1, 2)
--   Brand IDs: (1, 2)
-- ==============================================================================
WITH seller_totals AS (
    SELECT
        p.seller_id,
        COUNT(DISTINCT oi.order_id) AS total_orders,
        SUM(oi.quantity)::BIGINT AS total_quantity,
        SUM(oi.subtotal) AS total_revenue
    FROM order_item oi
    JOIN product p
      ON p.product_id = oi.product_id
    WHERE oi.order_date >= DATE '2025-01-01'::TIMESTAMP
      AND oi.order_date < DATE '2025-06-01'::TIMESTAMP
      AND NOT oi.is_deleted
      AND NOT p.is_deleted
      AND p.category_id IN (1, 2)
      AND p.brand_id IN (1, 2)
      AND NOT EXISTS (
          SELECT 1
          FROM "order" o
          WHERE o.order_id = oi.order_id
            AND o.is_deleted
      )
    GROUP BY p.seller_id
)
SELECT
    s.seller_id,
    s.seller_name::TEXT,
    st.total_orders,
    st.total_quantity,
    st.total_revenue
FROM seller_totals st
JOIN seller s
  ON s.seller_id = st.seller_id
WHERE NOT s.is_deleted
ORDER BY s.seller_id;
-- END REPORT 03 | report_seller_performance

-- ==============================================================================
-- REPORT 04 | TOP PRODUCTS PER BRAND
-- Function: report_top_products_per_brand
-- Item-date window; seller filtering precedes Top-N ranking within each brand.
-- Literal values:
--   Start date: DATE '2025-01-01'
--   End date: DATE '2025-06-01'
--   Seller IDs: (1, 2)
--   Top N: 5
-- ==============================================================================
WITH product_sales AS (
    SELECT b.brand_id, b.brand_name, p.product_id, p.product_name,
           SUM(oi.quantity)::BIGINT AS total_quantity,
           SUM(oi.subtotal) AS total_revenue
    FROM order_item oi
    JOIN product p ON p.product_id = oi.product_id
    JOIN brand b ON b.brand_id = p.brand_id
    WHERE oi.order_date >= DATE '2025-01-01'::TIMESTAMP
      AND oi.order_date < DATE '2025-06-01'::TIMESTAMP
      AND p.seller_id IN (1, 2)
      AND NOT oi.is_deleted
      AND NOT EXISTS (SELECT 1 FROM "order" o WHERE o.order_id = oi.order_id AND o.is_deleted)
      AND NOT p.is_deleted AND NOT b.is_deleted
    GROUP BY b.brand_id, b.brand_name, p.product_id, p.product_name
), ranked AS (
    SELECT ps.*, ROW_NUMBER() OVER (
        PARTITION BY ps.brand_id
        ORDER BY ps.total_quantity DESC, ps.total_revenue DESC, ps.product_id
    ) AS brand_rank
    FROM product_sales ps
)
SELECT r.brand_id, r.brand_name::TEXT, r.product_id, r.product_name::TEXT,
       r.total_quantity, r.total_revenue
FROM ranked r
WHERE r.brand_rank <= 5
ORDER BY r.brand_id, r.brand_rank;
-- END REPORT 04 | report_top_products_per_brand

-- ==============================================================================
-- REPORT 05 | ORDER STATUS SUMMARY
-- Function: report_order_status_summary
-- Order-date window; each qualifying order contributes its full total once.
-- Literal values:
--   Start date: DATE '2025-01-01'
--   End date: DATE '2025-06-01'
--   Seller IDs: (1, 2)
--   Category IDs: (1, 2)
-- ==============================================================================
SELECT
    o.status,
    COUNT(*) AS total_orders,
    SUM(o.total_amount) AS total_revenue
FROM "order" o
WHERE o.order_date >= DATE '2025-01-01'::TIMESTAMP
  AND o.order_date < DATE '2025-06-01'::TIMESTAMP
  AND NOT o.is_deleted
  AND EXISTS (
      SELECT 1
      FROM order_item oi
      JOIN product p ON p.product_id = oi.product_id
      WHERE oi.order_id = o.order_id
        AND NOT oi.is_deleted AND NOT p.is_deleted
        AND p.seller_id IN (1, 2)
        AND p.category_id IN (1, 2)
  )
GROUP BY o.status
ORDER BY o.status;
-- END REPORT 05 | report_order_status_summary

-- ==============================================================================
-- REPORT 06 | MONTHLY FULL-ORDER REVENUE
-- Function: report_monthly_order_revenue
-- Order-date window; full totals include orders without active items.
-- Literal values:
--   Start date: DATE '2025-01-01'
--   End date: DATE '2025-06-01'
-- ==============================================================================
SELECT DATE_TRUNC('month', o.order_date)::DATE AS month,
       COUNT(*) AS total_orders, SUM(o.total_amount) AS total_revenue
FROM "order" o
WHERE o.order_date >= DATE '2025-01-01'::TIMESTAMP
  AND o.order_date < DATE '2025-06-01'::TIMESTAMP AND NOT o.is_deleted
GROUP BY 1 ORDER BY 1;
-- END REPORT 06 | report_monthly_order_revenue

-- ==============================================================================
-- REPORT 07 | ORDERS BY SELLER
-- Function: report_orders_by_seller
-- Order-date window; seller matches qualify full order rows, not item-only totals.
-- Literal values:
--   Start date: DATE '2025-01-01'
--   End date: DATE '2025-06-01'
--   Seller IDs: (1, 2)
-- ==============================================================================
SELECT o.order_id, o.order_code, o.customer_id, o.order_date, o.status, o.total_amount
FROM "order" o
WHERE o.order_date >= DATE '2025-01-01'::TIMESTAMP
  AND o.order_date < DATE '2025-06-01'::TIMESTAMP AND NOT o.is_deleted
  AND EXISTS (
      SELECT 1 FROM order_item oi JOIN product p ON p.product_id = oi.product_id
      WHERE oi.order_id = o.order_id AND p.seller_id IN (1, 2)
        AND NOT oi.is_deleted AND NOT p.is_deleted
  )
ORDER BY o.order_date, o.order_id;
-- END REPORT 07 | report_orders_by_seller

-- ==============================================================================
-- REPORT 08 | ITEMS BY PRODUCT
-- Function: report_items_by_product
-- Item-date window; excludes deleted items only, not deleted parents/products.
-- Literal values:
--   Start date: DATE '2025-01-01'
--   End date: DATE '2025-06-01'
--   Product IDs: (1, 2)
-- ==============================================================================
SELECT oi.order_item_id, oi.order_item_code, oi.order_id, oi.product_id,
       oi.order_date, oi.quantity, oi.unit_price, oi.subtotal
FROM order_item oi
WHERE oi.order_date >= DATE '2025-01-01'::TIMESTAMP
  AND oi.order_date < DATE '2025-06-01'::TIMESTAMP AND NOT oi.is_deleted
  AND oi.product_id IN (1, 2)
ORDER BY oi.order_date, oi.order_item_id;
-- END REPORT 08 | report_items_by_product

-- ==============================================================================
-- REPORT 09 | HIGHEST-VALUE ORDERS
-- Function: report_highest_value_orders
-- Order-date window; global amount ranking, then order ID for ties.
-- Literal values:
--   Start date: DATE '2025-01-01'
--   End date: DATE '2025-06-01'
--   Top N: 1
-- ==============================================================================
SELECT o.order_id, o.order_code, o.customer_id, o.order_date, o.status, o.total_amount
FROM "order" o
WHERE o.order_date >= DATE '2025-01-01'::TIMESTAMP
  AND o.order_date < DATE '2025-06-01'::TIMESTAMP AND NOT o.is_deleted
ORDER BY o.total_amount DESC, o.order_id
LIMIT 1;
-- END REPORT 09 | report_highest_value_orders

-- ==============================================================================
-- REPORT 10 | GLOBAL TOP PRODUCTS
-- Function: report_top_products
-- Order-date window; global quantity ranking, then product ID for ties.
-- Literal values:
--   Start date: DATE '2025-01-01'
--   End date: DATE '2025-06-01'
--   Top N: 20
-- ==============================================================================
WITH product_totals AS (
    SELECT oi.product_id, SUM(oi.quantity) AS total_quantity,
           SUM(oi.subtotal) AS total_revenue
    FROM order_item oi JOIN "order" o ON o.order_id = oi.order_id
    WHERE o.order_date >= DATE '2025-01-01'::TIMESTAMP
      AND o.order_date < DATE '2025-06-01'::TIMESTAMP
      AND NOT oi.is_deleted AND NOT o.is_deleted
    GROUP BY oi.product_id
)
SELECT p.product_id, p.product_code, p.product_name,
       t.total_quantity, t.total_revenue
FROM product_totals t JOIN product p ON p.product_id = t.product_id
WHERE NOT p.is_deleted
ORDER BY t.total_quantity DESC, p.product_id
LIMIT 20;
-- END REPORT 10 | report_top_products

-- ==============================================================================
-- REPORT 11 | SELLER SALES
-- Function: report_seller_sales
-- Order-date window; distinct product types/orders, line rows, units, item revenue.
-- Literal values:
--   Start date: DATE '2025-01-01'
--   End date: DATE '2025-06-01'
--   Seller IDs: (1, 2)
-- ==============================================================================
WITH seller_totals AS (
    SELECT p.seller_id, COUNT(DISTINCT oi.product_id) AS distinct_products_sold,
           COUNT(DISTINCT oi.order_id) AS total_orders,
           COUNT(*) AS total_item_rows, SUM(oi.quantity) AS total_quantity,
           SUM(oi.subtotal) AS total_revenue
    FROM order_item oi
    JOIN product p ON p.product_id = oi.product_id
    JOIN "order" o ON o.order_id = oi.order_id
    WHERE o.order_date >= DATE '2025-01-01'::TIMESTAMP
      AND o.order_date < DATE '2025-06-01'::TIMESTAMP
      AND p.seller_id IN (1, 2)
      AND NOT oi.is_deleted AND NOT p.is_deleted AND NOT o.is_deleted
    GROUP BY p.seller_id
)
SELECT s.seller_id, s.seller_code, s.seller_name, t.distinct_products_sold,
       t.total_orders, t.total_item_rows, t.total_quantity, t.total_revenue
FROM seller_totals t JOIN seller s ON s.seller_id = t.seller_id
WHERE NOT s.is_deleted
ORDER BY t.total_quantity DESC, s.seller_id;
-- END REPORT 11 | report_seller_sales

-- ==============================================================================
-- REPORT 12 | PRODUCT/MONTH REVENUE
-- Function: report_product_monthly_revenue
-- Order-date window; group item subtotals and units by parent-order month/product.
-- Literal values:
--   Start date: DATE '2025-01-01'
--   End date: DATE '2025-06-01'
--   Product IDs: (1, 2)
-- ==============================================================================
WITH monthly_totals AS (
    SELECT DATE_TRUNC('month', o.order_date)::DATE AS month, oi.product_id,
           SUM(oi.quantity) AS total_quantity, SUM(oi.subtotal) AS total_revenue
    FROM order_item oi JOIN "order" o ON o.order_id = oi.order_id
    WHERE o.order_date >= DATE '2025-01-01'::TIMESTAMP
      AND o.order_date < DATE '2025-06-01'::TIMESTAMP
      AND oi.product_id IN (1, 2)
      AND NOT oi.is_deleted AND NOT o.is_deleted
    GROUP BY 1, oi.product_id
)
SELECT t.month, p.product_id, p.product_code, p.product_name,
       t.total_quantity, t.total_revenue
FROM monthly_totals t JOIN product p ON p.product_id = t.product_id
WHERE NOT p.is_deleted
ORDER BY t.month, p.product_id;
-- END REPORT 12 | report_product_monthly_revenue
