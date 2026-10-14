-- Runnable examples for all 13 requirements; install functions.sql first.
-- Original analytical IDs remain stable for snapshots and equivalence tests.

-- benchmark-query: 01_monthly_revenue
-- Full order totals, including active orders without items.
SELECT * FROM report_monthly_order_revenue(DATE '-infinity', DATE 'infinity');

-- benchmark-query: 02_orders_by_seller_and_date
-- Each qualifying order once; revenue is the full order amount.
SELECT * FROM report_orders_by_seller(DATE '2025-03-01', DATE '2025-04-01', ARRAY[1]);

-- benchmark-query: 03_items_by_product
-- Item deletion only; no parent/product deletion filtering.
SELECT * FROM report_items_by_product(DATE '-infinity', DATE 'infinity', ARRAY[1]);

-- benchmark-query: 04_highest_value_order
SELECT * FROM report_highest_value_orders(DATE '-infinity', DATE 'infinity', 1);

-- benchmark-query: 05_top_products_by_quantity
SELECT * FROM report_top_products(DATE '-infinity', DATE 'infinity', 20);

-- benchmark-query: 06_orders_by_seller_march_2025
-- Same seller aggregation as query 08; preserve this requirement's projection/order.
SELECT seller_id, seller_code, seller_name, total_orders, total_quantity, total_revenue
FROM report_seller_sales(DATE '2025-03-01', DATE '2025-04-01')
ORDER BY seller_id;

-- benchmark-query: 07_product_monthly_revenue
SELECT * FROM report_product_monthly_revenue(DATE '-infinity', DATE 'infinity');

-- benchmark-query: 08_products_sold_per_seller
SELECT * FROM report_seller_sales(DATE '-infinity', DATE 'infinity');

-- benchmark-query: monthly_revenue
SELECT * FROM report_monthly_revenue(DATE '2025-01-01', DATE '2025-06-01');

-- benchmark-query: daily_revenue
SELECT * FROM report_daily_revenue(DATE '2025-03-01', DATE '2025-04-01', ARRAY[1,2]);

-- benchmark-query: seller_performance
SELECT * FROM report_seller_performance(DATE '2025-01-01', DATE '2025-06-01', ARRAY[2], ARRAY[1]);

-- benchmark-query: top_products_per_brand
SELECT * FROM report_top_products_per_brand(DATE '2025-01-01', DATE '2025-06-01', ARRAY[1,2], 5);

-- benchmark-query: order_status_summary
SELECT * FROM report_order_status_summary(DATE '2025-01-01', DATE '2025-06-01', NULL, ARRAY[1,2]);
