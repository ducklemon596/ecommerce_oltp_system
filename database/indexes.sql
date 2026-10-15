-- Run each statement separately in autocommit mode (CONCURRENTLY cannot run
-- inside a transaction). This is the single source of performance-index DDL.
CREATE INDEX CONCURRENTLY IF NOT EXISTS order_active_date_idx
    ON "order" (order_date, order_id)
    INCLUDE (order_code, customer_id, status, total_amount)
    WHERE NOT is_deleted;

CREATE INDEX CONCURRENTLY IF NOT EXISTS order_active_amount_idx
    ON "order" (total_amount DESC, order_id)
    INCLUDE (order_code, customer_id, order_date, status)
    WHERE NOT is_deleted;

CREATE INDEX CONCURRENTLY IF NOT EXISTS order_item_active_product_idx
    ON order_item (product_id, order_date, order_item_id)
    INCLUDE (order_item_code, order_id, quantity, unit_price, subtotal)
    WHERE NOT is_deleted;

CREATE INDEX CONCURRENTLY IF NOT EXISTS product_active_seller_idx
    ON product (seller_id, product_id)
    WHERE NOT is_deleted;
