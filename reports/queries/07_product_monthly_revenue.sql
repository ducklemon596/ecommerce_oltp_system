SELECT date_trunc('month', o.order_date)::date AS month,
       p.product_id, p.product_code, p.product_name,
       sum(oi.quantity) AS total_quantity, sum(oi.subtotal) AS total_revenue
FROM order_item oi
JOIN product p ON p.product_id = oi.product_id
JOIN "order" o ON o.order_id = oi.order_id AND o.order_date = oi.order_date
WHERE NOT oi.is_deleted AND NOT p.is_deleted AND NOT o.is_deleted
GROUP BY 1, p.product_id, p.product_code, p.product_name
ORDER BY month, p.product_id;
