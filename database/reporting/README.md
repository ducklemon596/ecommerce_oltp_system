# SQL reporting layer

[functions.sql](functions.sql)
is the single production source for **12 functions covering 13 requirements**.
The five existing function signatures are preserved. [examples.sql](examples.sql) contains runnable calls for all 13 requirements.

## Requirements inventory and mapping

The inventory below was assembled before migration. Revenue is gross recorded
revenue across every status, including cancelled and returned. No report filters
on `product.is_active`. “Active” below means `NOT is_deleted`.

| Requirement | Output and grain; ordering | Filters, joins, soft deletion | Canonical function / disposition |
|---|---|---|---|
| A01 Monthly revenue | month, total_orders, total_revenue; month order | All-history order totals; active orders only, including orders with no active items | `report_monthly_order_revenue` — preserved |
| A02 Orders by seller/date | order_id/code, customer_id, order_date, status, full total_amount; date/ID order | March, seller 1 generalized; order dates; active order plus EXISTS through active item/product; seller deletion ignored | `report_orders_by_seller` — preserved |
| A03 Items by product | item_id/code, order_id, product_id, order_date, quantity, unit_price, subtotal; date/item ID order | Product 1 generalized; item dates; exclude deleted items only; no order/product join | `report_items_by_product` — preserved |
| A04 Highest-value order | order_id/code, customer_id, order_date, status, total_amount; amount DESC then ID | Active orders; all history generalized to date window and Top-N | `report_highest_value_orders` — preserved |
| A05 Top products globally | product_id/code/name, total_quantity, total_revenue; quantity DESC then product ID, top 20 | Active items/orders/products; full history generalized; order-date window | `report_top_products` — preserved |
| A06 Seller orders in March | seller_id/code/name, distinct total_orders, total_quantity, item total_revenue; seller ID order | March order dates; active sellers/products/items/orders | `report_seller_sales` — merged with A08 via column projection and seller-ID ordering |
| A07 Product/month revenue | month, product_id/code/name, total_quantity, item total_revenue; month/product order | Active products/items/orders; order dates; all history generalized | `report_product_monthly_revenue` — preserved |
| A08 Products sold per seller | seller_id/code/name, distinct_products_sold, total_orders, total_item_rows, total_quantity, item total_revenue; quantity DESC then seller ID | Active sellers/products/items/orders; order dates; history generalized | `report_seller_sales` — preserved, also covers A06 |
| D01 Monthly item revenue | month, distinct total_orders with active items, total_quantity, item total_revenue; month order | Item dates; active items/orders; product deletion ignored | `report_monthly_revenue` — preserved signature |
| D02 Daily item revenue | date, distinct total_orders, total_quantity, matching item total_revenue; date order | Item dates; optional product array; active items/orders; product deletion ignored | `report_daily_revenue` — preserved signature |
| D03 Seller performance | seller_id/name, distinct total_orders, total_quantity, item total_revenue; seller ID order | Item dates; optional category/brand arrays; active sellers/products/items/orders; category/brand deletion ignored | `report_seller_performance` — preserved signature |
| D04 Top products per brand | brand_id/name, product_id/name, total_quantity, item total_revenue; rank within brand by quantity DESC, revenue DESC, ID | Item dates; seller array; active brands/products/items/orders; seller deletion ignored | `report_top_products_per_brand` — preserved signature |
| D05 Status summary | status, total_orders, full-order total_revenue; status order | Order dates; optional seller/category arrays qualify orders via active items/products; count each order once | `report_order_status_summary` — preserved signature |

**One redundant standalone aggregation is eliminated:** A06 uses the richer A08
seller summary with a March window, a projection, and seller-ID ordering.
A01 and D01 stay separate: full order totals and active-item subtotals need not
agree. A05 is global Top-N, D04 is Top-N within each brand. Product types, line
rows, distinct orders, and units remain separate metrics. D03 preserves its
item-date contract; A06/A08 preserve their order-date semantics.

## Catalog and usage

Every function begins with `p_start_date DATE, p_end_date DATE` and uses
`[start_date, end_date)`. Use `DATE '-infinity'` / `DATE 'infinity'`
for all history. NULL date bounds match no rows, as in the existing functions.
NULL arrays disable their filter; empty arrays match no rows. A NULL or
nonpositive Top-N returns no rows. Empty groups are omitted.

| Function | Remaining parameters (defaults) | Output / requirement |
|---|---|---|
| `report_monthly_order_revenue` | none | A01 |
| `report_orders_by_seller` | `p_seller_ids INTEGER[] = NULL` | A02 |
| `report_items_by_product` | `p_product_ids INTEGER[] = NULL` | A03 |
| `report_highest_value_orders` | `p_top_n INTEGER = 1` | A04 |
| `report_top_products` | `p_top_n INTEGER = 20` | A05 |
| `report_seller_sales` | `p_seller_ids INTEGER[] = NULL` | A06, A08 |
| `report_product_monthly_revenue` | `p_product_ids INTEGER[] = NULL` | A07 |
| `report_monthly_revenue` | none | D01 |
| `report_daily_revenue` | `p_product_ids INTEGER[] = NULL` | D02 |
| `report_seller_performance` | `p_category_ids INTEGER[] = NULL, p_brand_ids INTEGER[] = NULL` | D03 |
| `report_top_products_per_brand` | `p_seller_ids INTEGER[] = NULL, p_top_n INTEGER = 10` | D04 |
| `report_order_status_summary` | `p_seller_ids INTEGER[] = NULL, p_category_ids INTEGER[] = NULL` | D05 |

Install after the application schema. Functions use the installation session's
search path; install in the same schema as the application tables. Using local
Compose credentials (or supply your configured connection):

```bash
PGPASSWORD=postgres psql -h localhost -U postgres -d ecommerce_oltp \
  -v ON_ERROR_STOP=1 -1 -f database/reporting/functions.sql
```

Installation is explicit; the loader remains focused on loading records.
This refactor does not deploy functions or change source indexes/records.

See [examples.sql](examples.sql) for runnable calls for every requirement. The
A06 block demonstrates the seller-summary projection and seller-ID ordering.

## Correctness and rewrite boundaries

`order_item.order_id` is NOT NULL with an FK to the order PK; deletion flags
are NOT NULL. With these constraints, rejecting deleted parents using
`NOT EXISTS` is equivalent to joining active parents. Removing a dimension
join is safe only if its existence/deletion checks are not required.

Historical validation found zero item/order date mismatches across 17,500,990
items. However, equality is **not a database constraint**. Existing dynamic
reports retain item-date behavior, while analytical order-date reports keep
the order timestamp. This avoids relying on an unenforced invariant for future
data. Added date filters and adjusted parent joins have not been benchmarked.

Top-products-per-brand uses the earlier direct product/brand join form for
seller filtering, retaining the current item-date behavior. This removes the
correlated seller subquery from the regressed rewrite. The earlier form
measured 2,146 ms versus the rewrite's 4,510 ms without workload indexes;
the exact consolidated variant needs measurements before claiming a speedup.
Existing query-level aggregates are reused; no persistent summaries are added.

Integration tests use the real schema and a temporary schema with rolled-back
fixture data. They compare all 13 requirements with bidirectional `EXCEPT ALL`
and cover optional arrays, soft deletion, differing item/order dates, orders
without active lines, multi-seller attribution, ranking ties, and signatures.

```bash
.venv/bin/python -m unittest discover -s tests/integration -p 'test_reporting.py' -v
.venv/bin/python -m unittest discover -s tests -v
```

Validated on 2026-10-14: **72 tests passed**, including 35 reporting integration
tests. Current database catalog checks confirmed validated item FKs and required
NOT NULL columns. Historical SQL checksums still match the recorded inputs.

## Workload and index matrix

D = `order_active_date_idx`; A = `order_active_amount_idx`;
I = `order_item_active_product_idx`; S = `product_active_seller_idx`.
These are relevant access paths, not independently measured speedups.

| Function(s) | Equality/range predicates and joins | Group/order pattern; selectivity | Relevant indexes |
|---|---|---|---|
| Monthly order revenue | Active order + order-date range | Month aggregate; broad ranges may scan | D may cover selective windows |
| Orders by seller | Seller list, order-date range; EXISTS product/item/order | Unique order list ordered date/ID | D + I + S; order PK |
| Items by product | Product list + item-date range | Selective line lookup ordered date/ID | I; multiple IDs may require sorting |
| Highest-value orders | Active order + order-date range | Amount DESC / ID / LIMIT | A; narrow date window may use D + sort |
| Global top products | Active item/order/product, order-date range | Broad global quantity aggregate | PKs; no proven extra-index benefit for history |
| Seller sales | Seller list + order-date range; product/item/order/seller | Distinct products/orders and units | I + S for selective sellers; broad scans otherwise |
| Product/month revenue | Optional product list + order-date range | Product/month aggregate | I for selective products; order/product PKs |
| Monthly item revenue | Item-date range, reject deleted parent | Broad month/distinct-order aggregate | I is not date-leading; no historical full-window gain |
| Daily item revenue | Product list + item-date range, active parent | Daily/distinct-order aggregate | I; order PK |
| Seller performance | Category/brand lists + item-date range; seller/product joins | Seller/distinct-order aggregate | I + S observed; no category/brand-leading index |
| Top products per brand | Seller list + item-date range; product/brand/order | Product aggregate, within-brand ranking | I + S plausible; PKs; exact variant unmeasured |
| Order status summary | Order-date range; optional seller/category EXISTS | Count orders once, sum full totals by status | I + S observed; D possible for narrow order windows |

## Index recommendations

Definitions have one source of truth: [indexes.sql](../indexes.sql).
All four are composite partial B-tree indexes (`WHERE NOT is_deleted`);
the first three have covering INCLUDE columns. PK and business-key UNIQUE
indexes protect constraints and loader UPSERT targets and should remain.

| Index | Historical evidence / target | Cost and overlap | Recommendation |
|---|---|---|---|
| `order_item_active_product_idx` | Product lookup: 300.248 → 4.110 ms. Dynamic daily: 759.503 → 196.181 ms, seller performance: 1,203.691 → 367.388 ms, status: 1,584.007 → 656.177 ms with the set. | 1,579.4 MiB; different leading key from UNIQUE (order_id, product_id), so not redundant. Wide INCLUDE columns cost storage/writes. | **Keep**, highest priority. Test a narrower replacement before changing coverage. |
| `order_active_amount_idx` | Highest-value lookup: **681.782 → 0.041 ms**, plan uses this ordered covering index. | 395.5 MiB; different leading key from the date index; no equivalent ordering path. | **Keep** for highest-value retrieval. Earlier advice calling baseline 0.682 ms was a unit error: it was 0.682 seconds. |
| `order_active_date_idx` | Seller/date query: 1,402.822 → 416.023 ms with D/I/S; plan uses an index-only March range scan. | 361.1 MiB; same rows as A but different ordering; no use in five sampled dynamic plans. | **Needs further benchmarking**, keep provisionally. **Consider removing** only if date/seller lookups are rare and an ablation shows low value. |
| `product_active_seller_idx` | Used in seller/date, seller sales, seller performance, and filtered status plans. | ~88 KiB; product PK is not seller-leading. | **Keep**, low cost; independent timing effect unisolated. |

All four were toggled together; plan usage does not establish independent
causality. Broad history aggregates saw little benefit. March seller summary
regressed 2,576 → 2,739 ms with the set. Dynamic top-products-per-brand also
remained slower than old SQL with indexes (2,146 → 2,978 ms): investigate the
query shape rather than dropping the useful product index.

Rolled-back INSERT trials: 20,000 orders took 254.259 → 311.941 ms (**+22.7%**);
19,973 items took 458.973 → 504.161 ms (**+9.8%**). These are combined-index costs,
not per-index costs or full-loader timings. Additional index storage was about
2.28 GiB on the captured dataset.

**Recommend adding: none yet.** Category/brand-leading product indexes lack
evidence when product has only 3,000 rows and fact access dominates. A
date-leading item index might help short windows, but broad five-month
aggregates do not justify it. No speculative index DDL is proposed or applied.

## Historical evidence and follow-up experiments

- [Analytical benchmark](../../reports/sql_optimization/README.md): original → rewritten → rewritten with indexes.
- [Dynamic benchmark](../../reports/dynamic_reports/README.md): old → October 13 rewrite → that rewrite with indexes. Its timings do not measure the new consolidated top-brand variant.
- [Original snapshot metadata](../../reports/sql_optimization/baseline/query_summary.json): single-run plans and result exports, not controlled medians.
- [Archived SQL](../../benchmarks/README.md): original/rewrite pairs and both historical function versions. Measurements remain unchanged by this refactor.

Most useful follow-ups: remove only D in an isolated clone while retaining I/S;
compare the consolidated top-brand function with both archives for selective
and broad seller arrays; test short versus broad dates; measure a slimmer I
replacement's read latency, size, INSERT/UPDATE/WAL costs. Randomize stage order
and record JIT/cache behavior. Existing benchmarks used one warm-up plus five
measured executions per query/stage with randomized query order and warm caches.

Future benchmarks replace stable `latest/` output directories. Frozen historical
reports require explicit `--overwrite`; no evidence is overwritten during cleanup.
To reproduce historical SQL select its archived candidate.

```bash
.venv/bin/python scripts/benchmark_dynamic_reports.py --prepare
.venv/bin/python scripts/benchmark_dynamic_reports.py --run
.venv/bin/python scripts/benchmark_dynamic_reports.py --cleanup
# After preparing a fresh clone, for the historical candidate:
.venv/bin/python scripts/benchmark_dynamic_reports.py --run \
  --candidate-sql benchmarks/dynamic_optimized_20261013.sql \
  --output reports/dynamic_reports/latest
```

The analytical runner reads named blocks from the archived original/rewrite SQL
files. The snapshot runner reads `database/reporting/examples.sql`: install the
functions first. Fixed cases and output directories are in
[cases.json](../../benchmarks/cases.json). Verification/repair behavior is unchanged;
audit output now lives under `reports/data_validation/latest/`.
