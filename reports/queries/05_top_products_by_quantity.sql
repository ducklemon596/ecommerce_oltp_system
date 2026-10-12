-- Top 20 products by units sold across all recorded statuses.
SELECT p.product_id, p.product_code, p.product_name,
       sum(oi.quantity) AS total_quantity, sum(oi.subtotal) AS total_revenue
FROM order_item oi
JOIN product p ON p.product_id = oi.product_id
JOIN "order" o ON o.order_id = oi.order_id AND o.order_date = oi.order_date
WHERE NOT oi.is_deleted AND NOT p.is_deleted AND NOT o.is_deleted
GROUP BY p.product_id, p.product_code, p.product_name
ORDER BY total_quantity DESC, p.product_id LIMIT 20;
