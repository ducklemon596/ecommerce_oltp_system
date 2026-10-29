-- Additional indexes selected by the consecutive warm-cache B3 experiment.
-- Equal frequency across 12 reporting functions; see the consolidated report
-- for absolute workload savings, regressions, storage and maintenance costs.
-- Execute explicitly after loading. Benchmarking did not deploy to the primary.
-- Standard CREATE INDEX and serial maintenance match the measured builds.
SET max_parallel_maintenance_workers = 0;

CREATE INDEX IF NOT EXISTS order_order_id_deleted_idx
    ON "order" (order_id)
    WHERE is_deleted;

CREATE INDEX IF NOT EXISTS order_item_product_order_cover_idx
    ON order_item (product_id, order_id)
    INCLUDE (order_date, quantity, subtotal)
    WHERE NOT is_deleted;

CREATE INDEX IF NOT EXISTS order_month_cover_idx
    ON "order" ((DATE_TRUNC('month', order_date)::DATE), order_id)
    INCLUDE (order_date, total_amount)
    WHERE NOT is_deleted;

CREATE INDEX IF NOT EXISTS order_item_month_order_cover_idx
    ON order_item ((DATE_TRUNC('month', order_date)::DATE), order_id)
    INCLUDE (order_date, quantity, subtotal)
    WHERE NOT is_deleted;

CREATE INDEX IF NOT EXISTS order_date_order_cover_idx
    ON "order" (order_date, order_id)
    INCLUDE (total_amount)
    WHERE NOT is_deleted;

CREATE INDEX IF NOT EXISTS order_amount_order_active_idx
    ON "order" (total_amount DESC, order_id)
    WHERE NOT is_deleted;

CREATE INDEX IF NOT EXISTS order_item_order_date_brin_idx
    ON order_item USING brin (order_date);
