-- Gross recorded revenue across all statuses; exclude soft-deleted orders.
SELECT date_trunc('month', order_date)::date AS month,
       count(*) AS total_orders, sum(total_amount) AS total_revenue
FROM "order"
WHERE NOT is_deleted
GROUP BY 1 ORDER BY 1;
