-- Deterministic tie-break: lowest order_id among equally valuable orders.
SELECT order_id, order_code, customer_id, order_date, status, total_amount
FROM "order" WHERE NOT is_deleted
ORDER BY total_amount DESC, order_id LIMIT 1;
