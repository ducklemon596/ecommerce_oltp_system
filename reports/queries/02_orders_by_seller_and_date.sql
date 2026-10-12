-- Example: seller 1, March 2025. EXISTS avoids duplicating multi-item orders.
SELECT o.order_id, o.order_code, o.customer_id, o.order_date, o.status, o.total_amount
FROM "order" o
WHERE NOT o.is_deleted
  AND o.order_date >= TIMESTAMP '2025-03-01'
  AND o.order_date < TIMESTAMP '2025-04-01'
  AND EXISTS (
      SELECT 1 FROM order_item oi JOIN product p ON p.product_id = oi.product_id
      WHERE oi.order_id = o.order_id AND oi.order_date = o.order_date
        AND p.seller_id = 1
        AND NOT oi.is_deleted AND NOT p.is_deleted
  )
ORDER BY o.order_date, o.order_id;
