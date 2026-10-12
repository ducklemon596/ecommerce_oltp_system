-- Example product_id = 1. Export all matching rows, without a LIMIT.
SELECT order_item_id, order_item_code, order_id, product_id, order_date,
       quantity, unit_price, subtotal
FROM order_item
WHERE product_id = 1 AND NOT is_deleted
ORDER BY order_date, order_item_id;
