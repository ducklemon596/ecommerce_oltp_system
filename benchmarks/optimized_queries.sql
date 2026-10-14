-- Historical SQL blocks; exact measured statements are preserved below.
-- These are benchmark inputs, not production reporting definitions.

-- benchmark-query: 05_top_products_by_quantity
WITH product_totals AS (
    SELECT
        oi.product_id,
        SUM(oi.quantity) AS total_quantity,
        SUM(oi.subtotal) AS total_revenue
    FROM order_item oi
    WHERE NOT oi.is_deleted
      AND NOT EXISTS (
          SELECT 1
          FROM "order" o
          WHERE o.order_id = oi.order_id
            AND o.is_deleted
      )
    GROUP BY oi.product_id
)
SELECT
    p.product_id,
    p.product_code,
    p.product_name,
    t.total_quantity,
    t.total_revenue
FROM product_totals t
JOIN product p ON p.product_id = t.product_id
WHERE NOT p.is_deleted
ORDER BY t.total_quantity DESC, p.product_id
LIMIT 20;

-- benchmark-query: 06_orders_by_seller_march_2025
WITH seller_totals AS (
    SELECT
        p.seller_id,
        COUNT(DISTINCT oi.order_id) AS total_orders,
        SUM(oi.quantity) AS total_quantity,
        SUM(oi.subtotal) AS total_revenue
    FROM order_item oi
    JOIN product p
      ON p.product_id = oi.product_id
    WHERE oi.order_date >= TIMESTAMP '2025-03-01'
      AND oi.order_date < TIMESTAMP '2025-04-01'
      AND NOT oi.is_deleted
      AND NOT p.is_deleted
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
    s.seller_code,
    s.seller_name,
    st.total_orders,
    st.total_quantity,
    st.total_revenue
FROM seller_totals st
JOIN seller s
  ON s.seller_id = st.seller_id
WHERE NOT s.is_deleted
ORDER BY s.seller_id;

-- benchmark-query: 07_product_monthly_revenue
WITH product_monthly_totals AS (
    SELECT
        DATE_TRUNC('month', oi.order_date)::date AS month,
        oi.product_id,
        SUM(oi.quantity) AS total_quantity,
        SUM(oi.subtotal) AS total_revenue
    FROM order_item oi
    WHERE NOT oi.is_deleted
      AND NOT EXISTS (
          SELECT 1
          FROM "order" o
          WHERE o.order_id = oi.order_id
            AND o.is_deleted
      )
    GROUP BY 1, oi.product_id
)
SELECT
    t.month,
    p.product_id,
    p.product_code,
    p.product_name,
    t.total_quantity,
    t.total_revenue
FROM product_monthly_totals t
JOIN product p
    ON p.product_id = t.product_id
WHERE NOT p.is_deleted
ORDER BY t.month, p.product_id;

-- benchmark-query: 08_products_sold_per_seller
WITH seller_totals AS (
    SELECT
        p.seller_id,
        COUNT(DISTINCT oi.product_id) AS distinct_products_sold,
        COUNT(DISTINCT oi.order_id) AS total_orders,
        COUNT(*) AS total_item_rows,
        SUM(oi.quantity) AS total_quantity,
        SUM(oi.subtotal) AS total_revenue
    FROM order_item oi
    JOIN product p
        ON p.product_id = oi.product_id
    WHERE NOT oi.is_deleted
      AND NOT p.is_deleted
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
    s.seller_code,
    s.seller_name,
    st.distinct_products_sold,
    st.total_orders,
    st.total_item_rows,
    st.total_quantity,
    st.total_revenue
FROM seller_totals st
JOIN seller s
    ON s.seller_id = st.seller_id
WHERE NOT s.is_deleted
ORDER BY st.total_quantity DESC, s.seller_id;
