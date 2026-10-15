-- Canonical reporting functions; install after the application's table schema.
-- Execute this file to deploy functions; numbered REPORT/END REPORT blocks separate definitions.
-- For one-off SELECTs without function deployment, use queries.sql instead.
-- queries.sql mirrors each body with sample literals; contract tests prevent drift.
-- All windows are [start_date, end_date). NULL ID arrays disable their filter;
-- empty arrays match no rows. Revenue includes every recorded order status.
-- Existing five function signatures and item-vs-order timestamp choices persist.
-- PK/FK and NOT NULL constraints are required for deleted-parent anti-joins.
-- SQL-level aggregate CTEs below reuse existing query logic; no stored summaries.

-- ==============================================================================
-- REPORT 01 | MONTHLY ITEM REVENUE
-- Purpose: active-item subtotals, not full order totals.
-- Inputs: item-date window; output: one row/month with sales. No product deletion filter.
-- Function: report_monthly_revenue
-- Terminal: uv run ecommerce report monthly
-- ==============================================================================
CREATE OR REPLACE FUNCTION report_monthly_revenue(
    p_start_date DATE,
    p_end_date DATE
)
RETURNS TABLE (
    month DATE,
    total_orders BIGINT,
    total_quantity BIGINT,
    total_revenue NUMERIC
)
LANGUAGE SQL STABLE PARALLEL SAFE
AS $$
    SELECT
        DATE_TRUNC('month', oi.order_date)::DATE AS month,
        COUNT(DISTINCT oi.order_id) AS total_orders,
        SUM(oi.quantity)::BIGINT AS total_quantity,
        SUM(oi.subtotal) AS total_revenue
    FROM order_item oi
    WHERE oi.order_date >= p_start_date::TIMESTAMP
      AND oi.order_date < p_end_date::TIMESTAMP
      AND NOT oi.is_deleted
      AND NOT EXISTS (
          SELECT 1
          FROM "order" o
          WHERE o.order_id = oi.order_id
            AND o.is_deleted
      )
    GROUP BY 1
    ORDER BY 1;
$$;
-- END REPORT 01 | report_monthly_revenue


-- ==============================================================================
-- REPORT 02 | DAILY ITEM REVENUE
-- Purpose: matching product subtotals, distinct orders/day.
-- Inputs: item-date window and optional product list; product deletion is ignored.
-- Function: report_daily_revenue
-- Terminal: uv run ecommerce report daily
-- ==============================================================================
CREATE OR REPLACE FUNCTION report_daily_revenue(
    p_start_date DATE,
    p_end_date DATE,
    p_product_ids INTEGER[] DEFAULT NULL
)
RETURNS TABLE (
    date DATE,
    total_orders BIGINT,
    total_quantity BIGINT,
    total_revenue NUMERIC
)
LANGUAGE SQL STABLE PARALLEL SAFE
AS $$
    SELECT
        oi.order_date::DATE AS date,
        COUNT(DISTINCT oi.order_id) AS total_orders,
        SUM(oi.quantity)::BIGINT AS total_quantity,
        SUM(oi.subtotal) AS total_revenue
    FROM order_item oi
    WHERE oi.order_date >= p_start_date::TIMESTAMP
      AND oi.order_date < p_end_date::TIMESTAMP
      AND (
          p_product_ids IS NULL
          OR oi.product_id = ANY(p_product_ids)
      )
      AND NOT oi.is_deleted
      AND NOT EXISTS (
          SELECT 1
          FROM "order" o
          WHERE o.order_id = oi.order_id
            AND o.is_deleted
      )
    GROUP BY 1
    ORDER BY 1;
$$;
-- END REPORT 02 | report_daily_revenue


-- ==============================================================================
-- REPORT 03 | SELLER PERFORMANCE
-- Purpose: attributed item revenue, each order once per seller.
-- Inputs: item-date window and optional category/brand IDs; those dimension deletion flags are ignored.
-- Function: report_seller_performance
-- Terminal: uv run ecommerce report seller-performance
-- ==============================================================================
CREATE OR REPLACE FUNCTION report_seller_performance(
    p_start_date DATE,
    p_end_date DATE,
    p_category_ids INTEGER[] DEFAULT NULL,
    p_brand_ids INTEGER[] DEFAULT NULL
)
RETURNS TABLE (
    seller_id INTEGER,
    seller_name TEXT,
    total_orders BIGINT,
    total_quantity BIGINT,
    total_revenue NUMERIC
)
LANGUAGE SQL STABLE PARALLEL SAFE
AS $$
    WITH seller_totals AS (
        SELECT
            p.seller_id,
            COUNT(DISTINCT oi.order_id) AS total_orders,
            SUM(oi.quantity)::BIGINT AS total_quantity,
            SUM(oi.subtotal) AS total_revenue
        FROM order_item oi
        JOIN product p
          ON p.product_id = oi.product_id
        WHERE oi.order_date >= p_start_date::TIMESTAMP
          AND oi.order_date < p_end_date::TIMESTAMP
          AND NOT oi.is_deleted
          AND NOT p.is_deleted
          AND (
              p_category_ids IS NULL
              OR p.category_id = ANY(p_category_ids)
          )
          AND (
              p_brand_ids IS NULL
              OR p.brand_id = ANY(p_brand_ids)
          )
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
$$;
-- END REPORT 03 | report_seller_performance


-- ==============================================================================
-- REPORT 04 | TOP PRODUCTS PER BRAND
-- Purpose: Top N within each brand; seller filter applies before aggregation.
-- NULL seller arrays disable the filter; empty arrays select nothing.
-- Use item timestamps to preserve the existing public function's contract.
-- Function: report_top_products_per_brand
-- Terminal: uv run ecommerce report top-products-per-brand
-- ==============================================================================
CREATE OR REPLACE FUNCTION report_top_products_per_brand(
    p_start_date DATE, p_end_date DATE,
    p_seller_ids INTEGER[] DEFAULT NULL, p_top_n INTEGER DEFAULT 10
)
RETURNS TABLE (
    brand_id INTEGER, brand_name TEXT, product_id INTEGER, product_name TEXT,
    total_quantity BIGINT, total_revenue NUMERIC
)
LANGUAGE SQL STABLE PARALLEL SAFE
AS $$
    WITH product_sales AS (
        SELECT b.brand_id, b.brand_name, p.product_id, p.product_name,
               SUM(oi.quantity)::BIGINT AS total_quantity,
               SUM(oi.subtotal) AS total_revenue
        FROM order_item oi
        JOIN "order" o ON o.order_id = oi.order_id
        JOIN product p ON p.product_id = oi.product_id
        JOIN brand b ON b.brand_id = p.brand_id
        WHERE oi.order_date >= p_start_date::TIMESTAMP
          AND oi.order_date < p_end_date::TIMESTAMP
          AND (p_seller_ids IS NULL OR p.seller_id = ANY(p_seller_ids))
          AND NOT oi.is_deleted AND NOT o.is_deleted
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
    WHERE r.brand_rank <= GREATEST(COALESCE(p_top_n, 0), 0)
    ORDER BY r.brand_id, r.brand_rank;
$$;
-- END REPORT 04 | report_top_products_per_brand

-- ==============================================================================
-- REPORT 05 | ORDER STATUS SUMMARY
-- Purpose: count each qualifying order once and sum its full total.
-- Inputs: order-date window, optional seller/category lists qualifying through active items/products.
-- Function: report_order_status_summary
-- Terminal: uv run ecommerce report status
-- ==============================================================================
CREATE OR REPLACE FUNCTION report_order_status_summary(
    p_start_date DATE,
    p_end_date DATE,
    p_seller_ids INTEGER[] DEFAULT NULL,
    p_category_ids INTEGER[] DEFAULT NULL
)
RETURNS TABLE (
    status VARCHAR(20),
    total_orders BIGINT,
    total_revenue NUMERIC
)
LANGUAGE SQL STABLE PARALLEL SAFE
AS $$
    SELECT
        o.status,
        COUNT(*) AS total_orders,
        SUM(o.total_amount) AS total_revenue
    FROM "order" o
    WHERE o.order_date >= p_start_date::TIMESTAMP
      AND o.order_date < p_end_date::TIMESTAMP
      AND NOT o.is_deleted
      AND (
          (
              p_seller_ids IS NULL
              AND p_category_ids IS NULL
          )
          OR EXISTS (
              SELECT 1
              FROM order_item oi
              JOIN product p
                ON p.product_id = oi.product_id
              WHERE oi.order_id = o.order_id
                AND NOT oi.is_deleted
                AND NOT p.is_deleted
                AND (
                    p_seller_ids IS NULL
                    OR p.seller_id = ANY(p_seller_ids)
                )
                AND (
                    p_category_ids IS NULL
                    OR p.category_id = ANY(p_category_ids)
                )
          )
      )
    GROUP BY o.status
    ORDER BY o.status;
$$;
-- END REPORT 05 | report_order_status_summary

-- ==============================================================================
-- REPORT 06 | MONTHLY FULL-ORDER REVENUE
-- Purpose: full order totals, including orders without active items.
-- Inputs: order-date window; output: month, order count, gross order revenue.
-- Function: report_monthly_order_revenue
-- Terminal: uv run ecommerce report monthly-orders
-- ==============================================================================
CREATE OR REPLACE FUNCTION report_monthly_order_revenue(
    p_start_date DATE, p_end_date DATE
)
RETURNS TABLE (month DATE, total_orders BIGINT, total_revenue NUMERIC)
LANGUAGE SQL STABLE PARALLEL SAFE
AS $$
    SELECT DATE_TRUNC('month', o.order_date)::DATE AS month,
           COUNT(*) AS total_orders, SUM(o.total_amount) AS total_revenue
    FROM "order" o
    WHERE o.order_date >= p_start_date::TIMESTAMP
      AND o.order_date < p_end_date::TIMESTAMP AND NOT o.is_deleted
    GROUP BY 1 ORDER BY 1;
$$;
-- END REPORT 06 | report_monthly_order_revenue

-- ==============================================================================
-- REPORT 07 | ORDERS BY SELLER
-- Purpose: full totals of orders containing matching sellers' active items.
-- NULL sellers means all active orders, even those without items; seller deletion is ignored.
-- Function: report_orders_by_seller
-- Terminal: uv run ecommerce report orders
-- ==============================================================================
CREATE OR REPLACE FUNCTION report_orders_by_seller(
    p_start_date DATE, p_end_date DATE, p_seller_ids INTEGER[] DEFAULT NULL
)
RETURNS TABLE (
    order_id INTEGER, order_code VARCHAR, customer_id INTEGER,
    order_date TIMESTAMP, status VARCHAR, total_amount NUMERIC
)
LANGUAGE SQL STABLE PARALLEL SAFE
AS $$
    SELECT o.order_id, o.order_code, o.customer_id, o.order_date, o.status, o.total_amount
    FROM "order" o
    WHERE o.order_date >= p_start_date::TIMESTAMP
      AND o.order_date < p_end_date::TIMESTAMP AND NOT o.is_deleted
      AND (p_seller_ids IS NULL OR EXISTS (
          SELECT 1 FROM order_item oi JOIN product p ON p.product_id = oi.product_id
          WHERE oi.order_id = o.order_id AND p.seller_id = ANY(p_seller_ids)
            AND NOT oi.is_deleted AND NOT p.is_deleted
      ))
    ORDER BY o.order_date, o.order_id;
$$;
-- END REPORT 07 | report_orders_by_seller

-- ==============================================================================
-- REPORT 08 | ITEMS BY PRODUCT
-- Purpose: active item rows only, irrespective of parent/dimension deletion.
-- Inputs: item-date window and optional product IDs; output ordered by item date/ID.
-- Function: report_items_by_product
-- Terminal: uv run ecommerce report items
-- ==============================================================================
CREATE OR REPLACE FUNCTION report_items_by_product(
    p_start_date DATE, p_end_date DATE, p_product_ids INTEGER[] DEFAULT NULL
)
RETURNS TABLE (
    order_item_id BIGINT, order_item_code VARCHAR, order_id INTEGER,
    product_id INTEGER, order_date TIMESTAMP, quantity INTEGER,
    unit_price NUMERIC, subtotal NUMERIC
)
LANGUAGE SQL STABLE PARALLEL SAFE
AS $$
    SELECT oi.order_item_id, oi.order_item_code, oi.order_id, oi.product_id,
           oi.order_date, oi.quantity, oi.unit_price, oi.subtotal
    FROM order_item oi
    WHERE oi.order_date >= p_start_date::TIMESTAMP
      AND oi.order_date < p_end_date::TIMESTAMP AND NOT oi.is_deleted
      AND (p_product_ids IS NULL OR oi.product_id = ANY(p_product_ids))
    ORDER BY oi.order_date, oi.order_item_id;
$$;
-- END REPORT 08 | report_items_by_product

-- ==============================================================================
-- REPORT 09 | HIGHEST-VALUE ORDERS
-- Purpose: deterministic global amount ranking in an order-date window.
-- NULL/nonpositive Top-N returns no rows. Default 1 preserves the original highest-order query.
-- Function: report_highest_value_orders
-- Terminal: uv run ecommerce report highest-orders
-- ==============================================================================
CREATE OR REPLACE FUNCTION report_highest_value_orders(
    p_start_date DATE, p_end_date DATE, p_top_n INTEGER DEFAULT 1
)
RETURNS TABLE (
    order_id INTEGER, order_code VARCHAR, customer_id INTEGER,
    order_date TIMESTAMP, status VARCHAR, total_amount NUMERIC
)
LANGUAGE SQL STABLE PARALLEL SAFE
AS $$
    SELECT o.order_id, o.order_code, o.customer_id, o.order_date, o.status, o.total_amount
    FROM "order" o
    WHERE o.order_date >= p_start_date::TIMESTAMP
      AND o.order_date < p_end_date::TIMESTAMP AND NOT o.is_deleted
    ORDER BY o.total_amount DESC, o.order_id
    LIMIT GREATEST(COALESCE(p_top_n, 0), 0);
$$;
-- END REPORT 09 | report_highest_value_orders

-- ==============================================================================
-- REPORT 10 | GLOBAL TOP PRODUCTS
-- Purpose: units DESC then product ID (no revenue tie-break).
-- Inputs: order-date window and Top-N. Aggregate before joining product labels.
-- Keep the order join: item/order timestamp equality is not a database constraint.
-- Function: report_top_products
-- Terminal: uv run ecommerce report top-products
-- ==============================================================================
CREATE OR REPLACE FUNCTION report_top_products(
    p_start_date DATE, p_end_date DATE, p_top_n INTEGER DEFAULT 20
)
RETURNS TABLE (
    product_id INTEGER, product_code VARCHAR, product_name TEXT,
    total_quantity BIGINT, total_revenue NUMERIC
)
LANGUAGE SQL STABLE PARALLEL SAFE
AS $$
    WITH product_totals AS (
        SELECT oi.product_id, SUM(oi.quantity) AS total_quantity,
               SUM(oi.subtotal) AS total_revenue
        FROM order_item oi JOIN "order" o ON o.order_id = oi.order_id
        WHERE o.order_date >= p_start_date::TIMESTAMP
          AND o.order_date < p_end_date::TIMESTAMP
          AND NOT oi.is_deleted AND NOT o.is_deleted
        GROUP BY oi.product_id
    )
    SELECT p.product_id, p.product_code, p.product_name,
           t.total_quantity, t.total_revenue
    FROM product_totals t JOIN product p ON p.product_id = t.product_id
    WHERE NOT p.is_deleted
    ORDER BY t.total_quantity DESC, p.product_id
    LIMIT GREATEST(COALESCE(p_top_n, 0), 0);
$$;
-- END REPORT 10 | report_top_products

-- ==============================================================================
-- REPORT 11 | SELLER SALES
-- Purpose: product types, distinct orders, line rows, units and item revenue.
-- Inputs: order-date window and optional seller IDs. Also covers the March seller summary.
-- Summed seller order counts are not a distinct platform order count.
-- Function: report_seller_sales
-- Terminal: uv run ecommerce report seller-sales
-- ==============================================================================
CREATE OR REPLACE FUNCTION report_seller_sales(
    p_start_date DATE, p_end_date DATE, p_seller_ids INTEGER[] DEFAULT NULL
)
RETURNS TABLE (
    seller_id INTEGER, seller_code VARCHAR, seller_name TEXT,
    distinct_products_sold BIGINT, total_orders BIGINT, total_item_rows BIGINT,
    total_quantity BIGINT, total_revenue NUMERIC
)
LANGUAGE SQL STABLE PARALLEL SAFE
AS $$
    WITH seller_totals AS (
        SELECT p.seller_id, COUNT(DISTINCT oi.product_id) AS distinct_products_sold,
               COUNT(DISTINCT oi.order_id) AS total_orders,
               COUNT(*) AS total_item_rows, SUM(oi.quantity) AS total_quantity,
               SUM(oi.subtotal) AS total_revenue
        FROM order_item oi
        JOIN product p ON p.product_id = oi.product_id
        JOIN "order" o ON o.order_id = oi.order_id
        WHERE o.order_date >= p_start_date::TIMESTAMP
          AND o.order_date < p_end_date::TIMESTAMP
          AND (p_seller_ids IS NULL OR p.seller_id = ANY(p_seller_ids))
          AND NOT oi.is_deleted AND NOT p.is_deleted AND NOT o.is_deleted
        GROUP BY p.seller_id
    )
    SELECT s.seller_id, s.seller_code, s.seller_name, t.distinct_products_sold,
           t.total_orders, t.total_item_rows, t.total_quantity, t.total_revenue
    FROM seller_totals t JOIN seller s ON s.seller_id = t.seller_id
    WHERE NOT s.is_deleted
    ORDER BY t.total_quantity DESC, s.seller_id;
$$;
-- END REPORT 11 | report_seller_sales

-- ==============================================================================
-- REPORT 12 | PRODUCT/MONTH REVENUE
-- Purpose: active product/item/parent subtotals and units.
-- Inputs: order-date window and optional product IDs. Month comes from the order,
-- as in the original requirement, even if an item's denormalized date differs.
-- Function: report_product_monthly_revenue
-- Terminal: uv run ecommerce report product-monthly
-- ==============================================================================
CREATE OR REPLACE FUNCTION report_product_monthly_revenue(
    p_start_date DATE, p_end_date DATE, p_product_ids INTEGER[] DEFAULT NULL
)
RETURNS TABLE (
    month DATE, product_id INTEGER, product_code VARCHAR, product_name TEXT,
    total_quantity BIGINT, total_revenue NUMERIC
)
LANGUAGE SQL STABLE PARALLEL SAFE
AS $$
    WITH monthly_totals AS (
        SELECT DATE_TRUNC('month', o.order_date)::DATE AS month, oi.product_id,
               SUM(oi.quantity) AS total_quantity, SUM(oi.subtotal) AS total_revenue
        FROM order_item oi JOIN "order" o ON o.order_id = oi.order_id
        WHERE o.order_date >= p_start_date::TIMESTAMP
          AND o.order_date < p_end_date::TIMESTAMP
          AND (p_product_ids IS NULL OR oi.product_id = ANY(p_product_ids))
          AND NOT oi.is_deleted AND NOT o.is_deleted
        GROUP BY 1, oi.product_id
    )
    SELECT t.month, p.product_id, p.product_code, p.product_name,
           t.total_quantity, t.total_revenue
    FROM monthly_totals t JOIN product p ON p.product_id = t.product_id
    WHERE NOT p.is_deleted
    ORDER BY t.month, p.product_id;
$$;
-- END REPORT 12 | report_product_monthly_revenue
