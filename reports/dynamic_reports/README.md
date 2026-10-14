# Dynamic SQL reports: performance review

Benchmark database: `ecommerce_oltp_dynamic_reports_bench`. Dataset: 5,000,000 orders and 17,500,990 order items. The source database was not modified.

## Method

The old report definitions were captured from the source database clone before replacement; optimized definitions came from the version now archived as [dynamic_optimized_20261013.sql](../../benchmarks/dynamic_optimized_20261013.sql). Both versions ran with one warm-up and five measured `EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS, FORMAT JSON)` executions without workload indexes. The optimized version was then measured again with four workload indexes. Primary/unique indexes and constraints remained intact. Each stage used the same data and parameters with randomized report order; caches were warm and not flushed; tables were analyzed before each stage. This separates the SQL rewrite from the additional index effect.

## Results

Execution times are PostgreSQL server medians. `Old → optimized` compares the versions without workload indexes; `optimized → indexed` isolates the index addition. Run-level timings and buffer/temp metrics are in [measurements.csv](measurements.csv); summary statistics are in [summary.csv](summary.csv).

| Report | Old SQL | Optimized SQL | Optimized + indexes | Old → optimized | Optimized → indexed | Plan notes |
|---|---:|---:|---:|---:|---:|---|
| `monthly_revenue` | 9931.082 ms | 7367.660 ms | 7395.203 ms | 1.35× | 1.00× | no workload index used; ranges overlap, treat median difference as noise |
| `daily_revenue` | 775.361 ms | 759.503 ms | 196.181 ms | 1.02× | 3.87× | order_item_active_product_idx |
| `seller_performance` | 1291.533 ms | 1203.691 ms | 367.388 ms | 1.07× | 3.28× | order_item_active_product_idx, product_active_seller_idx |
| `top_products_per_brand` | 2146.306 ms | 4509.973 ms | 2978.451 ms | 0.48× | 1.51× | order_item_active_product_idx |
| `order_status_summary` | 1566.548 ms | 1584.007 ms | 656.177 ms | 0.99× | 2.41× | order_item_active_product_idx, product_active_seller_idx |

## Function contracts

Both SQL versions were checked against independent reference queries using bidirectional `EXCEPT ALL`; every report returned zero differing rows in each version. All reports use a start-inclusive, end-exclusive date window. `NULL` optional ID arrays mean no filter; empty arrays match no rows. Product/category/brand/seller filters apply to matching line items. Revenue in product-scoped reports is item subtotal, while the status report uses order total amount and counts each order once.

| Function | Return columns |
|---|---|
| `report_monthly_revenue` | month, total_orders, total_quantity, total_revenue |
| `report_daily_revenue` | date, total_orders, total_quantity, total_revenue |
| `report_seller_performance` | seller_id, seller_name, total_orders, total_quantity, total_revenue |
| `report_top_products_per_brand` | brand_id, brand_name, product_id, product_name, total_quantity, total_revenue |
| `report_order_status_summary` | status, total_orders, total_revenue |

Soft-deleted orders and line items are excluded; product/seller/brand rows are excluded where they affect attribution. The top-products function returns the top N products per brand, ranked by quantity, then revenue, then product ID. Status output includes all statuses present in the schema.

## Index and plan interpretation

The indexed stage shows the combined impact of four workload indexes; it does not isolate each index's contribution. Category/brand filter fields are not independently indexed by this benchmark, and no partitions were added. Broad date-window aggregates may remain scan- and aggregation-bound.

Seven selected median-nearest plans illustrating rewrites, selective index benefits, and the top-brand regression are in [plans/](plans/). Full plans and the captured old SQL definition are in gitignored [raw/](raw/). Query contracts and tested parameters are in [validation.json](validation.json); PostgreSQL settings and row counts are in [environment.json](environment.json).

## Reproduce

From the repository root, after configuring `database.ini` and starting the PostgreSQL container:

```bash
.venv/bin/python scripts/benchmark_dynamic_reports.py --prepare
.venv/bin/python scripts/benchmark_dynamic_reports.py --run --output reports/dynamic_reports/latest \
  --candidate-sql benchmarks/dynamic_optimized_20261013.sql
.venv/bin/python scripts/benchmark_dynamic_reports.py --report-only --output /tmp/historical-dynamic-benchmark
.venv/bin/python scripts/benchmark_dynamic_reports.py --cleanup
```

The historical baseline is preserved in [dynamic_original.sql](../../benchmarks/dynamic_original.sql). The runner now installs this fixed baseline instead of relying on deployed functions. Future runs reuse `latest/`; replacing this frozen historical report requires `--overwrite`. The current production functions are in [functions.sql](../../database/reporting/functions.sql); this historical report does not measure later consolidated variants.
