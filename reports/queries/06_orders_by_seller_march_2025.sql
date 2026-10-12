-- Seller-level March summary; each seller counts each of their orders once.
-- Revenue is seller item revenue, not the full value of multi-seller orders.
SELECT s.seller_id, s.seller_code, s.seller_name,
       count(DISTINCT o.order_id) AS total_orders,
       sum(oi.quantity) AS total_quantity, sum(oi.subtotal) AS total_revenue
FROM seller s
JOIN product p ON p.seller_id = s.seller_id
JOIN order_item oi ON oi.product_id = p.product_id
JOIN "order" o ON o.order_id = oi.order_id AND o.order_date = oi.order_date
WHERE o.order_date >= TIMESTAMP '2025-03-01'
  AND o.order_date < TIMESTAMP '2025-04-01'
  AND NOT s.is_deleted AND NOT p.is_deleted
  AND NOT oi.is_deleted AND NOT o.is_deleted
GROUP BY s.seller_id, s.seller_code, s.seller_name ORDER BY s.seller_id;
