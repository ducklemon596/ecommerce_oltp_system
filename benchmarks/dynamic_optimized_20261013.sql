
-- ============================================================
-- 01. MONTHLY REVENUE REPORT
-- ============================================================
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


-- ============================================================
-- 02. DAILY REVENUE REPORT
-- ============================================================
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


-- ============================================================
-- 03. SELLER PERFORMANCE REPORT
-- ============================================================
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


-- ============================================================
-- 04. TOP PRODUCTS PER BRAND REPORT
-- ============================================================
CREATE OR REPLACE FUNCTION report_top_products_per_brand(
    p_start_date DATE,
    p_end_date DATE,
    p_seller_ids INTEGER[] DEFAULT NULL,
    p_top_n INTEGER DEFAULT 10
)
RETURNS TABLE (
    brand_id INTEGER,
    brand_name TEXT,
    product_id INTEGER,
    product_name TEXT,
    total_quantity BIGINT,
    total_revenue NUMERIC
)
LANGUAGE SQL STABLE PARALLEL SAFE
AS $$
    WITH product_totals AS (
        SELECT
            oi.product_id,
            SUM(oi.quantity)::BIGINT AS total_quantity,
            SUM(oi.subtotal) AS total_revenue
        FROM order_item oi
        WHERE oi.order_date >= p_start_date::TIMESTAMP
          AND oi.order_date < p_end_date::TIMESTAMP
          AND NOT oi.is_deleted
          AND (
              p_seller_ids IS NULL
              OR EXISTS (
                  SELECT 1
                  FROM product p_filter
                  WHERE p_filter.product_id = oi.product_id
                    AND p_filter.seller_id = ANY(p_seller_ids)
              )
          )
          AND NOT EXISTS (
              SELECT 1
              FROM "order" o
              WHERE o.order_id = oi.order_id
                AND o.is_deleted
          )
        GROUP BY oi.product_id
    ),
    ranked_products AS (
        SELECT
            b.brand_id,
            b.brand_name::TEXT AS brand_name,
            p.product_id,
            p.product_name::TEXT AS product_name,
            pt.total_quantity,
            pt.total_revenue,
            ROW_NUMBER() OVER (
                PARTITION BY b.brand_id
                ORDER BY
                    pt.total_quantity DESC,
                    pt.total_revenue DESC,
                    p.product_id
            ) AS brand_rank
        FROM product_totals pt
        JOIN product p
          ON p.product_id = pt.product_id
        JOIN brand b
          ON b.brand_id = p.brand_id
        WHERE NOT p.is_deleted
          AND NOT b.is_deleted
    )
    SELECT
        rp.brand_id,
        rp.brand_name,
        rp.product_id,
        rp.product_name,
        rp.total_quantity,
        rp.total_revenue
    FROM ranked_products rp
    WHERE rp.brand_rank <= GREATEST(COALESCE(p_top_n, 0), 0)
    ORDER BY rp.brand_id, rp.brand_rank;
$$;


-- ============================================================
-- 05. ORDER STATUS SUMMARY REPORT
-- ============================================================
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
