# SQL baseline results

Captured at: 2026-10-12T08:22:49.696724+00:00

Database: `ecommerce_oltp`. Server: PostgreSQL 16.15 (Debian 16.15-1.pgdg13+2) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit

See [report definitions and measurement method](../README.md).

Revenue includes all statuses and excludes soft-deleted rows. Seller
revenue is attributed from item subtotals. These are single executions
with existing indexes and cache state, before any optimization in this task.

## Data verification

Compared all 107 CSV files by business key and every source
attribute except database-managed `loaded_at`. Verified positional
IDs and source key uniqueness. SHA-256 digests are saved per file.

| Table | Source CSV rows | Database rows |
|---|---:|---:|
| brand | 20 | 20 |
| category | 25 | 25 |
| seller | 50 | 50 |
| customer | 30,000 | 30,000 |
| product | 3,000 | 3,000 |
| promotion | 30 | 30 |
| promotion_product | 500 | 500 |
| order | 5,000,000 | 5,000,000 |
| order_item | 17,500,990 | 17,500,990 |

Missing/different rows or invalid source IDs/keys: **0**.

The existing dataset was already loaded; no data reload was necessary.

Verification does not create checkpoints for historical loads.

## Runtime comparison

| Query | Result rows | Planning ms | Execution ms | Export seconds |
|---|---:|---:|---:|---:|
| [01_monthly_revenue](../queries/01_monthly_revenue.sql) | 5 | 0.476 | 2582.881 | 1.985 |
| [02_orders_by_seller_and_date](../queries/02_orders_by_seller_and_date.sql) | 105,583 | 0.549 | 1178.272 | 2.546 |
| [03_items_by_product](../queries/03_items_by_product.sql) | 25,154 | 0.104 | 600.330 | 0.408 |
| [04_highest_value_order](../queries/04_highest_value_order.sql) | 1 | 0.074 | 580.009 | 1.441 |
| [05_top_products_by_quantity](../queries/05_top_products_by_quantity.sql) | 20 | 0.403 | 5179.546 | 9.640 |
| [06_orders_by_seller_march_2025](../queries/06_orders_by_seller_march_2025.sql) | 50 | 0.455 | 4920.277 | 9.018 |
| [07_product_monthly_revenue](../queries/07_product_monthly_revenue.sql) | 14,399 | 0.260 | 9287.759 | 20.619 |
| [08_products_sold_per_seller](../queries/08_products_sold_per_seller.sql) | 50 | 0.319 | 15337.556 | 25.531 |

Execution ms is server time from EXPLAIN ANALYZE. Export seconds
measures the second execution plus network fetch and CSV writing.

## Result snapshots

### 01_monthly_revenue

[SQL](../queries/01_monthly_revenue.sql) · [Complete CSV](01_monthly_revenue.csv) · [Readable plan](01_monthly_revenue.plan.txt) · [Full plan with buffers](01_monthly_revenue.plan.json)

Showing 5 of 5 result rows.

| month | total_orders | total_revenue |
| --- | --- | --- |
| 2025-01-01 | 1026355 | 285289356527072.35 |
| 2025-02-01 | 927183 | 257645350397576.87 |
| 2025-03-01 | 1026526 | 286457180372571.04 |
| 2025-04-01 | 993412 | 276375414676847.17 |
| 2025-05-01 | 1026524 | 284308526998496.78 |

### 02_orders_by_seller_and_date

[SQL](../queries/02_orders_by_seller_and_date.sql) · [Complete CSV](02_orders_by_seller_and_date.csv) · [Readable plan](02_orders_by_seller_and_date.plan.txt) · [Full plan with buffers](02_orders_by_seller_and_date.plan.json)

Showing 5 of 105,583 result rows.

| order_id | order_code | customer_id | order_date | status | total_amount |
| --- | --- | --- | --- | --- | --- |
| 1953555 | ORD-001953555 | 4859 | 2025-03-01 00:00:41.682888 | DELIVERED | 521421503.43 |
| 1953557 | ORD-001953557 | 1094 | 2025-03-01 00:00:46.682888 | SHIPPED | 496292657.28 |
| 1953568 | ORD-001953568 | 2897 | 2025-03-01 00:01:15.682888 | DELIVERED | 310891765.97 |
| 1953586 | ORD-001953586 | 3428 | 2025-03-01 00:02:01.682888 | DELIVERED | 517752603.18 |
| 1953589 | ORD-001953589 | 4796 | 2025-03-01 00:02:10.682888 | CANCELLED | 86428610.80 |

### 03_items_by_product

[SQL](../queries/03_items_by_product.sql) · [Complete CSV](03_items_by_product.csv) · [Readable plan](03_items_by_product.plan.txt) · [Full plan with buffers](03_items_by_product.plan.json)

Showing 5 of 25,154 result rows.

| order_item_id | order_item_code | order_id | product_id | order_date | quantity | unit_price | subtotal |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 54 | OIT-000000016-01 | 16 | 1 | 2025-01-01 00:08:05.682888 | 3 | 49806456.87 | 149419370.61 |
| 740 | OIT-000000209-02 | 209 | 1 | 2025-01-01 00:16:30.682888 | 1 | 49806456.87 | 49806456.87 |
| 754 | OIT-000000214-01 | 214 | 1 | 2025-01-01 00:16:41.682888 | 2 | 49806456.87 | 99612913.74 |
| 1027 | OIT-000000288-05 | 288 | 1 | 2025-01-01 00:19:56.682888 | 5 | 49806456.87 | 249032284.35 |
| 1250 | OIT-000000354-03 | 354 | 1 | 2025-01-01 00:22:48.682888 | 5 | 49806456.87 | 249032284.35 |

### 04_highest_value_order

[SQL](../queries/04_highest_value_order.sql) · [Complete CSV](04_highest_value_order.csv) · [Readable plan](04_highest_value_order.plan.txt) · [Full plan with buffers](04_highest_value_order.plan.json)

Showing 1 of 1 result rows.

| order_id | order_code | customer_id | order_date | status | total_amount |
| --- | --- | --- | --- | --- | --- |
| 4731123 | ORD-004731123 | 22354 | 2025-05-23 21:07:24.682888 | DELIVERED | 1084273368.89 |

### 05_top_products_by_quantity

[SQL](../queries/05_top_products_by_quantity.sql) · [Complete CSV](05_top_products_by_quantity.csv) · [Readable plan](05_top_products_by_quantity.plan.txt) · [Full plan with buffers](05_top_products_by_quantity.plan.json)

Showing 5 of 20 result rows.

| product_id | product_code | product_name | total_quantity | total_revenue |
| --- | --- | --- | --- | --- |
| 440 | PRD-000440 | Visionary object-oriented firmware | 76347 | 1414949874728.76 |
| 370 | PRD-000370 | Synchronized attitude-oriented moderator | 76000 | 39739611120.00 |
| 588 | PRD-000588 | Robust real-time analyzer | 75993 | 3607185143059.20 |
| 22 | PRD-000022 | Assimilated 6thgeneration encryption | 75958 | 2722180590583.88 |
| 234 | PRD-000234 | Front-line optimizing Graphic Interface | 75926 | 1525279151946.14 |

### 06_orders_by_seller_march_2025

[SQL](../queries/06_orders_by_seller_march_2025.sql) · [Complete CSV](06_orders_by_seller_march_2025.csv) · [Readable plan](06_orders_by_seller_march_2025.plan.txt) · [Full plan with buffers](06_orders_by_seller_march_2025.plan.json)

Showing 5 of 50 result rows.

| seller_id | seller_code | seller_name | total_orders | total_quantity | total_revenue |
| --- | --- | --- | --- | --- | --- |
| 1 | SEL-00001 | Davis-Williams | 105583 | 330495 | 10298684650071.04 |
| 2 | SEL-00002 | Henderson, Brown and James | 63661 | 195102 | 3742800673954.92 |
| 3 | SEL-00003 | Valencia, Smith and Le | 84766 | 262576 | 6718601489682.34 |
| 4 | SEL-00004 | Mack-Peterson | 46777 | 142866 | 4237727858112.68 |
| 5 | SEL-00005 | Mckay Ltd | 59885 | 183595 | 5703414476871.80 |

### 07_product_monthly_revenue

[SQL](../queries/07_product_monthly_revenue.sql) · [Complete CSV](07_product_monthly_revenue.csv) · [Readable plan](07_product_monthly_revenue.plan.txt) · [Full plan with buffers](07_product_monthly_revenue.plan.json)

Showing 5 of 14,399 result rows.

| month | product_id | product_code | product_name | total_quantity | total_revenue |
| --- | --- | --- | --- | --- | --- |
| 2025-01-01 | 1 | PRD-000001 | Fundamental 5thgeneration benchmark | 16588 | 826189506559.56 |
| 2025-01-01 | 2 | PRD-000002 | Monitored upward-trending toolset | 16120 | 216242980917.60 |
| 2025-01-01 | 3 | PRD-000003 | Robust multimedia budgetary management | 16648 | 729266667514.56 |
| 2025-01-01 | 4 | PRD-000004 | Re-engineered content-based extranet | 16234 | 162756629051.32 |
| 2025-01-01 | 6 | PRD-000006 | Public-key systemic success | 16663 | 731716970177.00 |

### 08_products_sold_per_seller

[SQL](../queries/08_products_sold_per_seller.sql) · [Complete CSV](08_products_sold_per_seller.csv) · [Readable plan](08_products_sold_per_seller.plan.txt) · [Full plan with buffers](08_products_sold_per_seller.plan.json)

Showing 5 of 50 result rows.

| seller_id | seller_code | seller_name | distinct_products_sold | total_orders | total_item_rows | total_quantity | total_revenue |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 43 | SEL-00043 | Thornton, Hoffman and Rodriguez | 69 | 542339 | 566998 | 1700852 | 42588255124500.75 |
| 47 | SEL-00047 | Deleon-Henson | 79 | 537423 | 561812 | 1687384 | 53767047010569.89 |
| 1 | SEL-00001 | Davis-Williams | 63 | 513458 | 535695 | 1606791 | 50052180017684.64 |
| 39 | SEL-00039 | Newton and Sons | 75 | 472729 | 490896 | 1474743 | 34171716935893.46 |
| 45 | SEL-00045 | Williams LLC | 67 | 471679 | 490122 | 1470332 | 41203750380122.93 |

