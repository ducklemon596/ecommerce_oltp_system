# SQL Optimization & Index Benchmark

**Dataset:** 5,000,000 orders and 17,500,990 order items. **Captured:** 2026-10-13T08:51:54.607683+00:00. Measurements ran on isolated clone `ecommerce_oltp_sql_bench`; the primary database, data, and schema were preserved.

The [current function catalog](../../database/reporting/README.md) is separate
from the SQL measured here. Original statements and [rewrites](../../benchmarks/optimized_queries.sql)
are archived; the production reporting file is not substituted into this historical comparison.

## Executive summary

SQL rewrites delivered the broadest gains: queries 05–08 improved by 2.03×, 2.01×, 2.82×, and 1.43×. Indexes made selective lookups much faster (query 03: 73×; query 04: sub-millisecond lookup) and improved seller/date filtering (query 02: 3.37×). Broad history aggregates still scan and aggregate millions of item rows.

## Methodology

Three stages used one restored dataset and the same PostgreSQL settings: **A** original SQL/no four workload indexes; **B** rewritten SQL/no those indexes; **C** rewritten SQL/with all four. For queries 01–04, no separate rewrite was present, so A and B use the same SQL. Each query/stage had one warm-up and five measured `EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS, FORMAT JSON)` runs. Query order was randomized by a fixed seed each round; cache was warm and not flushed; tables were analyzed per index configuration. The source database was not used as a benchmark target.

All eight original/rewritten result sets were equivalent under bidirectional `EXCEPT ALL` (zero differing rows). Validation also found 0 order/item date mismatches, 0 missing order parents, and no null order IDs. See [validation.json](validation.json) and [environment.json](environment.json).

## Three-stage results

Speedup = A/B for SQL rewrites, B/C for the index set, and A/C overall. Values above 1 mean faster. Timings are medians; per-run values and buffer/temp counters are in [measurements.csv](measurements.csv), with a compact summary in [summary.csv](summary.csv).

| Query | A: Original / no index | B: Rewritten / no index | C: Rewritten / indexes | SQL speedup | Index speedup | Overall |
|---|---:|---:|---:|---:|---:|---:|
| [01_monthly_revenue](../../benchmarks/original_queries.sql) | 2658.359 ms | 2707.878 ms | 2610.737 ms | 0.98× | 1.04× | 1.02× |
| [02_orders_by_seller_and_date](../../benchmarks/original_queries.sql) | 1419.065 ms | 1402.822 ms | 416.023 ms | 1.01× | 3.37× | 3.41× |
| [03_items_by_product](../../benchmarks/original_queries.sql) | 305.508 ms | 300.248 ms | 4.110 ms | 1.02× | 73.05× | 74.33× |
| [04_highest_value_order](../../benchmarks/original_queries.sql) | 695.237 ms | 681.782 ms | 0.041 ms | 1.02× | 16628.83× | 16957.00× |
| [05_top_products_by_quantity](../../benchmarks/original_queries.sql) | 5371.496 ms | 2640.815 ms | 2595.601 ms | 2.03× | 1.02× | 2.07× |
| [06_orders_by_seller_march_2025](../../benchmarks/original_queries.sql) | 5165.916 ms | 2576.379 ms | 2739.249 ms | 2.01× | 0.94× | 1.89× |
| [07_product_monthly_revenue](../../benchmarks/original_queries.sql) | 9609.334 ms | 3407.863 ms | 3291.542 ms | 2.82× | 1.04× | 2.92× |
| [08_products_sold_per_seller](../../benchmarks/original_queries.sql) | 16741.586 ms | 11681.952 ms | 9810.570 ms | 1.43× | 1.19× | 1.71× |

## Interpretation and engineering decisions

| Query | Finding | Representative plan(s) |
|---|---|---|
| [01_monthly_revenue](../../benchmarks/original_queries.sql) | Full active-order aggregation and temporary sorting dominate; the targeted indexes do not reduce that work. | — |
| [02_orders_by_seller_and_date](../../benchmarks/original_queries.sql) | The combined date, seller-product, and product-first item indexes improve this selective query about 3.4×; exact per-index contribution was not isolated. | [C](plans/02_orders_by_seller_and_date_optimized_with_index.txt) |
| [03_items_by_product](../../benchmarks/original_queries.sql) | The product-first covering index replaces scanning the second column of the existing unique index plus a sort with an index-only lookup. | [B](plans/03_items_by_product_optimized_no_index.txt) · [C](plans/03_items_by_product_optimized_with_index.txt) |
| [04_highest_value_order](../../benchmarks/original_queries.sql) | The descending amount index turns a scan/sort into a one-row index lookup; interpret the large ratio cautiously because runtime is about 0.04 ms. | [C](plans/04_highest_value_order_optimized_with_index.txt) |
| [05_top_products_by_quantity](../../benchmarks/original_queries.sql) | Pre-aggregating by product before dimension joins roughly halves runtime and removes the large sort spill. The index set adds no meaningful gain. | [A](plans/05_top_products_by_quantity_original_no_index.txt) · [B](plans/05_top_products_by_quantity_optimized_no_index.txt) |
| [06_orders_by_seller_march_2025](../../benchmarks/original_queries.sql) | Filtering March items first roughly halves runtime; the indexed stage regressed about 6% versus the no-index rewrite. It still scans/aggregates many March items. | [B](plans/06_orders_by_seller_march_2025_optimized_no_index.txt) · [C](plans/06_orders_by_seller_march_2025_optimized_with_index.txt) |
| [07_product_monthly_revenue](../../benchmarks/original_queries.sql) | Pre-aggregation reduces runtime about 2.8× and avoids roughly 450k temporary blocks. Full item history remains the bottleneck. | [B](plans/07_product_monthly_revenue_optimized_no_index.txt) |
| [08_products_sold_per_seller](../../benchmarks/original_queries.sql) | Rewriting improves runtime about 1.4×; the index set adds about 1.2×, though full item aggregation remains expensive. Full item scan/aggregation remains about 9.8 seconds. | [C](plans/08_products_sold_per_seller_optimized_with_index.txt) |

Improvements around 5% or less with overlapping run ranges are treated as noise. Query 06's roughly 6% index-stage regression was consistent across observed runs. The index tests enabled all four together: plans show index use, but do not prove each index's independent timing contribution.

### Index assessment

| Index | Size | Observed workload use | Decision |
|---|---:|---|---|
| `order_active_date_idx` | 361.1 MiB | 02_orders_by_seller_and_date | Keep provisionally; contributes to seller/date lookup. Reassess if that workload is unimportant. |
| `order_active_amount_idx` | 395.5 MiB | 04_highest_value_order | Keep; highest-value lookup becomes an ordered one-row index access. |
| `order_item_active_product_idx` | 1579.4 MiB | 02_orders_by_seller_and_date, 03_items_by_product, 06_orders_by_seller_march_2025, 08_products_sold_per_seller | Keep; enables the 73× product lookup improvement and helps seller-filtered item access. Large storage cost. |
| `product_active_seller_idx` | 0.1 MiB | 02_orders_by_seller_and_date, 06_orders_by_seller_march_2025, 08_products_sold_per_seller | Needs further evaluation; small (~88 KiB) and used in three plans, but individual timing impact is unisolated. |

### Write maintenance check

The optional test inserted representative rows inside rolled-back transactions in the clone, after one warm-up and five measured trials per state. The four indexes were toggled as a set; data counts remained unchanged.

| Table | Rows | No-index median (min–max) | Indexed median (min–max) | Relative indexed time |
|---|---:|---:|---:|---:|
| `order` | 20,000 | 254.259 (252.200–270.808) ms | 311.941 (308.402–324.904) ms | 1.23× |
| `order_item` | 19,973 | 458.973 (454.770–466.340) ms | 504.161 (495.070–566.777) ms | 1.10× |

### Remaining bottlenecks

Queries 01, 05, 07, and 08 still perform broad aggregation work. In particular, query 07 processes full item history despite eliminating substantial temporary I/O, while query 08 remains about 9.8 seconds. Partitioning was not introduced or tested; these measurements alone do not establish a need for it.

## Reproduce

Requires the configured PostgreSQL source database, Docker access to `ecommerce-postgres`, and disk space for a database clone. The runner reads named SQL cases from `benchmarks/original_queries.sql` and `benchmarks/optimized_queries.sql`. Generated runs replace `reports/sql_optimization/latest/`; replacing this frozen historical report requires `--overwrite`. Existing clones are not overwritten.

```bash
.venv/bin/python scripts/benchmark_sql_optimization.py --prepare
.venv/bin/python scripts/benchmark_sql_optimization.py --run
.venv/bin/python scripts/benchmark_sql_optimization.py --write-test  # optional
.venv/bin/python scripts/benchmark_sql_optimization.py --report-only
.venv/bin/python scripts/benchmark_sql_optimization.py --cleanup
```

The runner verifies result equivalence and assumptions before timings, then writes concise root artifacts and selected readable plans. Full plans and intermediate captures are regenerated under gitignored `raw/`. The benchmark index DDL has one source of truth: [indexes.sql](../../database/indexes.sql).

## Cleanup provenance and current decisions

The summary/measurements CSVs and environment/validation JSON retain their
pre-migration bytes. Captured metadata may name the original relative
`indexes.sql` location; its unchanged DDL now lives at
[database/indexes.sql](../../database/indexes.sql). See the
[provenance manifest](../../docs/cleanup_provenance.json).

The historical measurement CSV is visually padded. The runner strips header/cell
padding when reading it, including quoted JSON metrics; the stored file is not
rewritten. Offline regeneration on a temporary copy retained all measured values.

Ten representative plans are published. Full captures and the superseded
single-run report/duplicate plans remain locally under ignored `raw/`; compact
single-run [timings](baseline/query_summary.json) and
[environment](baseline/environment.json) remain committed separately.

All four existing performance indexes remain approved and defined in one file.
Current guidance is to keep the product, amount, and small seller indexes and
retain the date index provisionally until an ablation isolates its benefit.
There is no approved removal or new candidate index. Constraint-backed indexes
remain part of the schema. The course partitioning requirement remains
[an undeployed experiment](../../experiments/partitioning/README.md).
