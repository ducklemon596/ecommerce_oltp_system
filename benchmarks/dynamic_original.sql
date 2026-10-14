CREATE OR REPLACE FUNCTION public.report_daily_revenue(p_start_date date, p_end_date date, p_product_ids integer[] DEFAULT NULL::integer[])
 RETURNS TABLE(date date, total_orders bigint, total_quantity bigint, total_revenue numeric)
 LANGUAGE sql
 STABLE PARALLEL SAFE
AS $function$
    SELECT o.order_date::DATE AS date,
           count(DISTINCT o.order_id) AS total_orders,
           sum(oi.quantity)::BIGINT AS total_quantity,
           sum(oi.subtotal) AS total_revenue
    FROM "order" AS o
    JOIN order_item AS oi ON oi.order_id = o.order_id
    WHERE o.order_date >= p_start_date::TIMESTAMP
      AND o.order_date < p_end_date::TIMESTAMP
      AND (p_product_ids IS NULL OR oi.product_id = ANY (p_product_ids))
      AND NOT o.is_deleted
      AND NOT oi.is_deleted
    GROUP BY 1
    ORDER BY 1;
$function$;


CREATE OR REPLACE FUNCTION public.report_monthly_revenue(p_start_date date, p_end_date date)
 RETURNS TABLE(month date, total_orders bigint, total_quantity bigint, total_revenue numeric)
 LANGUAGE sql
 STABLE PARALLEL SAFE
AS $function$
    SELECT date_trunc('month', o.order_date)::DATE AS month,
           count(DISTINCT o.order_id) AS total_orders,
           sum(oi.quantity)::BIGINT AS total_quantity,
           sum(oi.subtotal) AS total_revenue
    FROM "order" AS o
    JOIN order_item AS oi ON oi.order_id = o.order_id
    WHERE o.order_date >= p_start_date::TIMESTAMP
      AND o.order_date < p_end_date::TIMESTAMP
      AND NOT o.is_deleted
      AND NOT oi.is_deleted
    GROUP BY 1
    ORDER BY 1;
$function$;


CREATE OR REPLACE FUNCTION public.report_order_status_summary(p_start_date date, p_end_date date, p_seller_ids integer[] DEFAULT NULL::integer[], p_category_ids integer[] DEFAULT NULL::integer[])
 RETURNS TABLE(status character varying, total_orders bigint, total_revenue numeric)
 LANGUAGE sql
 STABLE PARALLEL SAFE
AS $function$
    SELECT o.status,
           count(*) AS total_orders,
           sum(o.total_amount) AS total_revenue
    FROM "order" AS o
    WHERE o.order_date >= p_start_date::TIMESTAMP
      AND o.order_date < p_end_date::TIMESTAMP
      AND NOT o.is_deleted
      AND (
          (p_seller_ids IS NULL AND p_category_ids IS NULL)
          OR EXISTS (
              SELECT 1
              FROM order_item AS oi
              JOIN product AS p ON p.product_id = oi.product_id
              WHERE oi.order_id = o.order_id
                AND NOT oi.is_deleted
                AND NOT p.is_deleted
                AND (p_seller_ids IS NULL OR p.seller_id = ANY (p_seller_ids))
                AND (p_category_ids IS NULL OR p.category_id = ANY (p_category_ids))
          )
      )
    GROUP BY o.status
    ORDER BY o.status;
$function$;


CREATE OR REPLACE FUNCTION public.report_seller_performance(p_start_date date, p_end_date date, p_category_ids integer[] DEFAULT NULL::integer[], p_brand_ids integer[] DEFAULT NULL::integer[])
 RETURNS TABLE(seller_id integer, seller_name text, total_orders bigint, total_quantity bigint, total_revenue numeric)
 LANGUAGE sql
 STABLE PARALLEL SAFE
AS $function$
    SELECT s.seller_id,
           s.seller_name,
           count(DISTINCT o.order_id) AS total_orders,
           sum(oi.quantity)::BIGINT AS total_quantity,
           sum(oi.subtotal) AS total_revenue
    FROM order_item AS oi
    JOIN "order" AS o ON o.order_id = oi.order_id
    JOIN product AS p ON p.product_id = oi.product_id
    JOIN seller AS s ON s.seller_id = p.seller_id
    WHERE o.order_date >= p_start_date::TIMESTAMP
      AND o.order_date < p_end_date::TIMESTAMP
      AND (p_category_ids IS NULL OR p.category_id = ANY (p_category_ids))
      AND (p_brand_ids IS NULL OR p.brand_id = ANY (p_brand_ids))
      AND NOT o.is_deleted
      AND NOT oi.is_deleted
      AND NOT p.is_deleted
      AND NOT s.is_deleted
    GROUP BY s.seller_id, s.seller_name
    ORDER BY s.seller_id;
$function$;


CREATE OR REPLACE FUNCTION public.report_top_products_per_brand(p_start_date date, p_end_date date, p_seller_ids integer[] DEFAULT NULL::integer[], p_top_n integer DEFAULT 10)
 RETURNS TABLE(brand_id integer, brand_name text, product_id integer, product_name text, total_quantity bigint, total_revenue numeric)
 LANGUAGE sql
 STABLE PARALLEL SAFE
AS $function$
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
        WHERE o.order_date >= p_start_date::TIMESTAMP
          AND o.order_date < p_end_date::TIMESTAMP
          AND (p_seller_ids IS NULL OR p.seller_id = ANY (p_seller_ids))
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
    WHERE rp.brand_rank <= greatest(p_top_n, 0)
    ORDER BY rp.brand_id, rp.brand_rank;
$function$;
