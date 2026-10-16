# Reporting catalog

Owns SQL aggregation, attribution, filters, and rankings. Python only binds
parameters and exports results; it does not duplicate business calculations.

## File overview

| File | Purpose |
|---|---|
| [functions.sql](functions.sql) | Canonical definitions of all 12 parameterized PostgreSQL reports |
| [queries.sql](queries.sql) | The same SQL bodies, in catalog order, with executable example literals |
| [original_queries.sql](original_queries.sql) | Original baseline SELECTs retained for educational comparison, with provenance and scope warnings |

Standalone examples are complete SELECTs, not function calls.
Contract tests detect divergence; integration tests compare values, ordering, and
column names on fixtures that include soft deletions and mismatched item dates.

Both SQL files use matching numbered `REPORT` / `END REPORT` comment blocks.
Each block identifies the function, purpose, and relevant inputs. In pgAdmin,
select one complete block from `queries.sql` to run a report; execute
`functions.sql` only when deploying or replacing the callable functions.

[original_queries.sql](original_queries.sql) preserves the authentic, unoptimized
SELECT implementations recovered from Git commit `fc35293`. It is a benchmark
baseline and educational reference, not another production reporting layer.
Original all-history scopes and timestamp choices are documented in that file;
the final functions and examples above remain the optimized implementations.

## Coverage: 13 requirements, 12 functions

| Original requirement | CLI report | Canonical function | Important distinction |
|---|---|---|---|
| Monthly revenue report, including units | `monthly` | `report_monthly_revenue` | Active item revenue; distinct orders with active items |
| Daily revenue with product list | `daily` | `report_daily_revenue` | Item-date grain; revenue only from matching products |
| Seller performance with category/brand filters | `seller-performance` | `report_seller_performance` | Attributed item revenue, distinct orders per seller |
| Top products within each brand | `top-products-per-brand` | `report_top_products_per_brand` | Top-N **per brand**, optional seller list |
| Orders status summary | `status` | `report_order_status_summary` | Count each order once; sum its **full order total** |
| Total revenue per month | `monthly-orders` | `report_monthly_order_revenue` | Full order totals, including orders without active items |
| Orders filtered by seller and date | `orders` | `report_orders_by_seller` | Full order rows qualifying through matching items |
| Filter order items by product | `items` | `report_items_by_product` | Active items only; no parent/product deletion filtering |
| Highest-value order | `highest-orders` | `report_highest_value_orders` | Global amount ranking; default Top-N = 1 |
| Products with highest quantity sold | `top-products` | `report_top_products` | Global quantity ranking; default Top-N = 20 |
| Orders by seller in March 2025 | `seller-sales` | `report_seller_sales` | March window and a projection of seller-summary columns |
| Revenue per product per month | `product-monthly` | `report_product_monthly_revenue` | Product/month item totals, using the parent order date |
| Products sold per seller | `seller-sales` | `report_seller_sales` | Distinct product types, orders, line rows, units, item revenue |

Only the two seller-sales requirements share an aggregation. Monthly order totals
and item subtotals are not interchangeable. Global rankings and within-brand
rankings also remain separate. Seller performance retains item-date semantics;
seller sales uses the parent order date.

## Parameters and semantics

Every function starts with `p_start_date DATE, p_end_date DATE` and uses a
start-inclusive, end-exclusive window. Examples use January 1–June 1, 2025.
Use `DATE '-infinity'` / `DATE 'infinity'` for all history.

- `NULL` date bounds produce no rows. Empty groups are omitted.
- Optional ID lists are `INTEGER[]`: `NULL` disables a filter; `ARRAY[]::INTEGER[]`
  matches nothing. Product/seller aggregates attribute only matching line revenue.
- Top-N is `p_top_n INTEGER`: default 10 within each brand, 20 globally, 1 for
  highest-value orders. NULL/nonpositive values return no rows.
- Revenue includes all recorded statuses, including cancelled/returned; this is
  gross recorded revenue, not recognized or net revenue.
- Status filtering qualifies each order through one active item/product matching
  both seller and category filters; it does not multiply order totals.
- “Active” means `NOT is_deleted`; no report filters `product.is_active`.

Monthly/daily item reports ignore product deletion. Seller performance excludes
deleted sellers/products/items/orders, but not deleted category/brand dimensions.
Within-brand ranking excludes deleted brands/products/items/orders, not sellers.
Seller sales excludes deleted sellers/products/items/orders. Item export excludes
only deleted items. Other order-based reports exclude deleted orders.

Item-date reports retain their existing timestamp contracts. Product/month and
seller-sales reports use the order timestamp: item/order timestamp equality is
not a database constraint. Deleted-parent anti-joins require the schema's NOT NULL
order ID and foreign key. Do not remove these constraints.

Within-brand ties use quantity DESC, revenue DESC, then product ID. Global product
ties use product ID after quantity; highest-order ties use order ID after amount.
Seller-sales order counts cannot be summed into a distinct platform order count.

## Usage and maintenance

### Automatic CSV exports

```bash
uv run report                         # save every report
uv run report monthly                 # save one report
uv run report all --only monthly daily
uv run report monthly --output-dir reports/custom
uv run report list
uv run ecommerce report --help
uv run ecommerce report monthly --start 2025-03-01 --end 2025-04-01
uv run ecommerce report seller-performance --categories 6,7 --brands 1,2
uv run ecommerce report top-products-per-brand --sellers 1,2 --top 5
uv run ecommerce report status --sellers 1,2 --categories 6,7
uv run ecommerce report daily --products null
uv run ecommerce report daily --products ""
uv run ecommerce report daily --products 1,2 --limit 10 --config database.ini --section postgresql
uv run ecommerce report items --help
```

Each report exposes only its applicable filters. All use March 2025 by default;
the standalone SQL file retains its explicit January–May sample window.
Omit a filter or pass `null` to disable it; `""` or `[]` passes an empty array and
matches nothing. Top-N defaults follow the functions. `--limit` defaults to 50
CSV rows per report and reports truncation, without changing calculations or
ranking. Increase it to export more rows. It is not a query-cost limit: large
aggregates still process all qualifying data.

Results are saved automatically under `reports/results/` (or `--output-dir`), not
printed as terminal tables. Each CSV contains column headers and a unique filename
such as `monthly_2025-03-01_2025-04-01_a1b2c3d4e5f6.csv`; repeated runs keep previous
files. Empty results produce header-only CSVs. Only saved-file confirmations and
row-limit warnings appear in the terminal. `list` and help still print normally.

Bare `uv run report` and `uv run ecommerce report` save all 12 reports. Use a report
name for one filtered report, or `all --only monthly daily` for a subset.
All/subset mode uses NULL filters and each function's default Top-N, with shared
date/connection/output/limit options. If a report fails, its CSV is not created;
other reports continue, and the command exits nonzero with the failed report names.
All required functions must already be deployed for a complete export.

The lightweight runner is [reporting.py](../../src/ecommerce_oltp_system/reporting.py).
It binds dates/arrays/limits as parameters and quotes only whitelisted function
identifiers. Results are read in a read-only transaction and the connection closes
on success or failure. `report list` and help need no database. Execution requires
the functions to be deployed already; missing functions produce deployment guidance,
not automatic DDL. The runner does not duplicate any reporting business SQL.

### SQL deployment and direct queries

Install the functions in the same schema as the application tables; see the
[root quick start](../../README.md#sql-reporting). Functions use the session search
path. The loader deliberately does not deploy reporting functions or indexes.

```sql
SELECT * FROM report_daily_revenue(
    DATE '2025-03-01', DATE '2025-04-01', ARRAY[1, 2]
);

-- The March seller-order requirement is a projection of the richer sales report.
SELECT seller_id, seller_code, seller_name, total_orders, total_quantity, total_revenue
FROM report_seller_sales(DATE '2025-03-01', DATE '2025-04-01')
ORDER BY seller_id;
```

For educational inspection or pgAdmin EXPLAIN, use the full statements in
`queries.sql`. Change every occurrence of a sample parameter within its statement.
When changing logic, edit the function body first, mirror that body with the
documented literals in `queries.sql`, and run the database-free contract tests:

```bash
uv run python -m unittest discover -s tests/unit -v
```

For value/ordering checks against PostgreSQL, follow the
[integration-test guide](../../tests/integration/README.md) using a dedicated test database.

Approved indexes remain in [../indexes.sql](../indexes.sql). Fresh full-dataset
loading and current-query measurements are in the
[performance report](../../reports/sql_optimization/README.md), including broad
and selective cases, callable-versus-standalone plans, regressions, and index costs.
Recorded parameters matter: these timings do not predict every filter combination
or include the CLI's row limit, network transfer, or CSV export time.
