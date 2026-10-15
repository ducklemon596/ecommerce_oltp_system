# Reporting catalog

[functions.sql](functions.sql) is the canonical SQL implementation.
[queries.sql](queries.sql) contains the **same 12 SQL bodies with literal sample
parameters**, in the same order: complete SELECTs, not function calls.
Contract tests detect divergence; integration tests compare values, ordering, and
column names on fixtures that include soft deletions and mismatched item dates.

Both SQL files use matching numbered `REPORT` / `END REPORT` comment blocks.
Each block identifies the function, purpose, and relevant inputs. In pgAdmin,
select one complete block from `queries.sql` to run a report; execute
`functions.sql` only when deploying or replacing the callable functions.

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

### Terminal reports

```bash
uv run ecommerce report list
uv run ecommerce report --help
uv run ecommerce report monthly --start 2025-03-01 --end 2025-04-01
uv run ecommerce report seller-performance --categories 1,2 --brands 2,10,30
uv run ecommerce report top-products-per-brand --sellers 1,2 --top 5
uv run ecommerce report status --sellers 1,2 --categories 3
uv run ecommerce report daily --products null
uv run ecommerce report daily --products ""
uv run ecommerce report daily --products 1,2 --limit 10 --config database.ini --section postgresql
uv run ecommerce report items --help
```

Each report exposes only its applicable filters. All use March 2025 by default;
the standalone SQL file retains its explicit January–May sample window.
Omit a filter or pass `null` to disable it; `""` or `[]` passes an empty array and
matches nothing. Top-N defaults follow the functions. `--limit` defaults to 50
displayed rows and reports truncation, without changing calculations or ranking.
It is not a query-cost limit: large aggregates still process all qualifying data.

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
documented literals in `queries.sql`, and run:

```bash
uv run python -m unittest discover -s tests -v
```

Approved indexes remain in [../indexes.sql](../indexes.sql). Historical measurements
and trade-offs live in the [performance report](../../reports/sql_optimization/README.md).
They do not establish timings for every current function/filter combination.
