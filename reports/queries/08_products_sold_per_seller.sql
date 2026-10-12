-- Distinguish distinct product types, item rows, orders, and units sold.
SELECT s.seller_id, s.seller_code, s.seller_name,
       count(DISTINCT p.product_id) AS distinct_products_sold,
       count(DISTINCT o.order_id) AS total_orders,
       count(*) AS total_item_rows, sum(oi.quantity) AS total_quantity,
       sum(oi.subtotal) AS total_revenue
FROM seller s
JOIN product p ON p.seller_id = s.seller_id
JOIN order_item oi ON oi.product_id = p.product_id
JOIN "order" o ON o.order_id = oi.order_id AND o.order_date = oi.order_date
WHERE NOT s.is_deleted AND NOT p.is_deleted
  AND NOT oi.is_deleted AND NOT o.is_deleted
GROUP BY s.seller_id, s.seller_code, s.seller_name
ORDER BY total_quantity DESC, s.seller_id;
