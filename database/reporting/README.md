# SQL Reporting Catalog

**Twelve PostgreSQL functions** turn transactional orders and order items into management summaries, seller drill-downs, and product rankings. **Business calculations live in SQL**; Python passes parameters and exports the results to CSV.

## Explore the reports

| Workload | Typical questions | CLI examples |
|---|---|---|
| **Broad reporting** | How much did we sell? How are sellers and products performing? | `report broad` |
| **Rankings / Top-K** | Which orders and products rank highest? | `report ranking` |
| **Drill-down** | What happened for a seller, brand, category, or date range? | `report drill-down` |

A category command executes a convenient **batch of existing functions**. Categories can share functions, and they are **not** the same as the simulated benchmark sessions.

### All 12 available functions

| CLI name | PostgreSQL function | What it returns |
|---|---|---|
| `monthly` | `report_monthly_revenue` | Monthly item revenue, units, and distinct orders. |
| `daily` | `report_daily_revenue` | Daily item revenue, optionally filtered by products. |
| `seller-performance` | `report_seller_performance` | Seller-level sales and order metrics with category/brand filters. |
| `top-products-per-brand` | `report_top_products_per_brand` | Top products **within each brand**, not globally. |
| `status` | `report_order_status_summary` | Order counts and **full order totals** by status. |
| `monthly-orders` | `report_monthly_order_revenue` | Monthly revenue from full order totals, not item subtotals. |
| `orders` | `report_orders_by_seller` | Orders matching seller and date conditions. |
| `items` | `report_items_by_product` | Order items matching a product filter. |
| `highest-orders` | `report_highest_value_orders` | Highest-value orders, default Top-N = 1. |
| `top-products` | `report_top_products` | Products ranked by quantity sold, default Top-N = 20. |
| `seller-sales` | `report_seller_sales` | Seller sales, distinct product types, items, units, and revenue. |
| `product-monthly` | `report_product_monthly_revenue` | Item revenue by product and month, using the parent order date. |

The original specification had **13 requirements but 12 functions**: the March seller-order requirement is a column projection of `report_seller_sales`, not a duplicated aggregation.

## Key SQL design decisions

| Decision | Why it matters |
|---|---|
| **Filter with existence checks (`EXISTS` / semi-join)** | An order with multiple matching items should be counted **once**, not duplicated by a one-to-many join. |
| **Respect deleted-parent exclusions (`NOT EXISTS` / anti-join where applicable)** | Apply soft-deletion rules without unnecessarily scanning or duplicating parent rows. |
| **Keep order totals separate from item revenue** | A status summary or monthly order-total report should not silently switch to summing selected line items. |
| **Use the correct timestamp** | Some reports use `order_item.order_date`; others use the parent `order.order_date`. These are **not guaranteed to match**. |
| **Define stable Top-K tie-breakers** | Equal quantities or amounts must still produce predictable ranking results. |
| **Keep calculations in PostgreSQL** | The Python reporter does not reimplement joins or aggregations, reducing duplicated business logic. |

These choices are about **correct results first**, followed by measurable performance improvements. The [optimization case study](../../reports/SQL_Optimization_README.md) compares original/reworked SQL and selective, broad, and Top-K plans.

### Important business semantics

- **Date windows** are start-inclusive and end-exclusive: `[start_date, end_date)`. All functions take `p_start_date DATE, p_end_date DATE` first. Use `DATE '-infinity'` and `DATE 'infinity'` for an all-history window; NULL date bounds return no rows.
- **Optional ID arrays:** `NULL` means no filter; an empty `INTEGER[]` matches nothing. Only matching item revenue is attributed to filtered products/sellers.
- **Revenue** includes all recorded order statuses, including cancelled or returned orders. It represents **gross recorded revenue**, not recognized or net revenue.
- **Soft deletions** are deliberately report-specific. Item exports exclude deleted items only; seller performance and seller sales exclude deleted sellers, products, items, and orders. Monthly/daily item reports do not filter deleted products. See [`functions.sql`](functions.sql) for each report's exact rules.
- **Rankings:** Within-brand Top-N defaults to 10, global product Top-N to 20, and highest orders to 1. NULL/nonpositive limits yield no rows. Tie-breakers are documented in SQL.

## Run the reports

Start with the [local setup guide](../../docs/usage/usage-guide.md) to deploy the reporting functions and configure PostgreSQL. Then, from the repository root:

```bash
# Discover reports and parameters
uv run ecommerce report list

# Run a complete category; CSVs are saved automatically
uv run ecommerce report broad --start 2025-01-01 --end 2025-06-01
uv run ecommerce report ranking --start 2025-01-01 --end 2025-06-01 --top 5
uv run ecommerce report drill-down --sellers 1,2 --start 2025-03-01 --end 2025-04-01

# Or run one function
uv run ecommerce report monthly --start 2025-03-01 --end 2025-04-01
uv run ecommerce report status --sellers 1,2 --categories 6,7
```

Exports are UTF-8 CSV files with headers under `reports/results/` (category runs use subdirectories). Each run gets a unique filename. The default export cap is **50 rows per report**; `--limit` changes output size, **not** how much data PostgreSQL must aggregate. Failed exports do not leave partial CSVs, and report connections are read-only.

To run SQL directly in pgAdmin, select a full `REPORT` block from [`queries.sql`](queries.sql). To deploy or replace callable PostgreSQL functions, use [`functions.sql`](functions.sql) via the explicit setup workflow. **Report execution never deploys SQL automatically.**

```sql
SELECT *
FROM report_daily_revenue(
    DATE '2025-03-01',
    DATE '2025-04-01',
    ARRAY[1, 2]
);
```

## Source files and validation

| File | Use it for |
|---|---|
| [`functions.sql`](functions.sql) | **Canonical** definitions of 12 parameterized reporting functions. |
| [`queries.sql`](queries.sql) | Matching standalone `SELECT` statements with example literals, useful for `EXPLAIN`. |
| [`original_queries.sql`](original_queries.sql) | Preserved original SQL for educational comparison; not another deployment layer. |

When changing a report, update the function body and its matching standalone query, then verify semantics with unit contracts and PostgreSQL integration tests. Tests cover filtering, soft deletion, timestamps, result values, ordering, and output columns.

```bash
uv run python -m unittest discover -s tests/unit -v
```

For database-backed checks, use a **dedicated test database** as described in the [integration testing guide](../../tests/integration/README.md). Standalone-query benchmark timings do not include function invocation, network transfer, or CSV export time.
