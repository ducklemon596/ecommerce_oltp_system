## Synthetic-data generator and PostgreSQL loader

This version generates and validates `brand`, `category`, `seller`, `product`,
`customer`, `promotion`, and `promotion_product`, writes each table to CSV, and
streams `order` and `order_item` into CSV parts. The loader creates the complete
PostgreSQL schema and loads all nine tables.

Generate all nine tables with one deterministic command:

or:
`uv run python -m ecommerce_oltp_system.generate`
```bash
uv run ecommerce-oltp-system
```

The command writes:

```text
data/brand.csv
data/category.csv
data/seller.csv
data/customer.csv
data/product.csv
data/promotion.csv
data/promotion_product.csv
data/orders/order_part_0001.csv
data/orders/...
data/order_items/order_item_part_0001.csv
data/order_items/...
```

Generate only the seven smaller base tables with
`uv run ecommerce-oltp-system --base-only`.

## Order-only benchmark

Regenerate only the 5,000,000 orders and approximately 17,500,000 order items:

```bash
uv run ecommerce-generate-orders
```

The command reads `data/customer.csv` and `data/product.csv`, then streams paired
parts to:

```text
data/orders/order_part_0001.csv
data/order_items/order_item_part_0001.csv
...
```

Each part contains at most 100,000 orders by default. Change the benchmark size or
part size without editing code:

```bash
uv run ecommerce-generate-orders --orders 500000 --orders-per-file 50000
```

Use `--output-dir` to write the generated folders somewhere other than `data`.
The command reports per-part and aggregate elapsed time and throughput. Expected

Run the tests:

```bash
uv run python -m unittest discover -s tests
```

The generator uses seed `42`. Stable business keys use the forms `BRD-00001`,
`CAT-00001`, `SEL-00001`, `PRD-000001`, and `PRO-00001`. PostgreSQL-managed
primary keys are absent from the files. Orders use `ORD-000000001` and later codes.

Integer foreign keys are based on expected PostgreSQL IDs:

- `category.parent_category_id` points to expected category IDs `1..5`.
- Product `brand_id`, `category_id`, and `seller_id` point to the deterministic
  row positions of their parent files. Product categories use only IDs `6..25`.
- Promotion-product `promotion_id` and `product_id` point to deterministic row
  positions in `promotion.csv` and `product.csv`.

The loader preserves CSV row order and verifies that generated IDs match those
positions. A database with unrelated rows or matching business keys under
different IDs is rejected because this version does not remap foreign keys.

All records include audit columns. `created_by` is `faker_batch`; update and
deletion fields are empty; `is_deleted` is false. `loaded_at` stays empty in
CSV because PostgreSQL sets it when the row is loaded.

## PostgreSQL schema and loading

Copy the safe template to a local configuration file, set your PostgreSQL values,
then create the schema and load the complete dataset:

```bash
cp database.ini.example database.ini
# Update database.ini with your host, database, user, and password.
uv run ecommerce-load-data
```

The default section is `[postgresql]`; `port` is optional. The actual
`database.ini` is ignored by Git to protect credentials.

The schema is defined in `src/ecommerce_oltp_system/loader/sql/schema.sql`. To
create only the tables, use `uv run ecommerce-load-data --schema-only`. To load
into an already-created schema, use `uv run ecommerce-load-data --skip-schema`.
A custom CSV directory can be supplied with `--data-dir`.

Files load in dependency order: `brand`, `category`, `seller`, `customer`,
`product`, `promotion`, then `promotion_product`. Each file is one transaction.
The loader locks the target table, synchronizes its serial sequence to its
current maximum primary key, and performs parameterized UPSERTs in CSV order.
An error rolls back every row from that file while leaving previously committed
table files unchanged. `loaded_at` is database-managed and is refreshed when an
existing row is updated.

UPSERT keys are the table's stable source identifiers: the code columns for
brand, category, seller, product, and promotion; email for customer; and the
`(promotion_id, product_id)` pair for promotion-product mappings.

The numeric foreign keys require brand, category, seller, product, and promotion
IDs to match their one-based CSV positions. The loader checks this invariant and
rolls back the current table if it is violated. ID remapping by business code is
intentionally not implemented in this version.


## Large-table loading benchmark report

Measurements used five generated part files: 500,000 order rows and 1,750,656 matching order-item rows. Each run used one transaction and a 30,000-row execute_values page size. Final benchmark targets were logged tables; staging tables were unlogged. One warm-up was excluded, then five randomized measured runs were collected for every configuration. Values are medians; ranges are minimum–maximum elapsed times.

### Feature-overhead benchmark

#### Order

| Method | Configuration | Median s | Rows/s | Range s | Δ previous | Δ base |
|---|---|---:|---:|---:|---:|---:|
| execute_values | Base | 8.99 | 55,616 | 8.84–9.41 | — | — |
| execute_values | + CHECK | 9.20 | 54,348 | 8.97–9.45 | +2.3% | +2.3% |
| execute_values | + PK / UNIQUE | 10.59 | 47,223 | 10.27–10.86 | +15.1% | +17.8% |
| execute_values | + FK | 12.51 | 39,975 | 12.48–12.69 | +18.1% | +39.1% |
| execute_values | + UPSERT | 14.57 | 34,320 | 14.33–14.64 | +16.5% | +62.1% |
| COPY → staging → final | Base | 1.80 | 277,247 | 1.76–1.97 | — | — |
| COPY → staging → final | + CHECK | 1.92 | 260,771 | 1.91–1.98 | +6.3% | +6.3% |
| COPY → staging → final | + PK / UNIQUE | 3.32 | 150,416 | 3.20–3.53 | +73.4% | +84.3% |
| COPY → staging → final | + FK | 5.35 | 93,519 | 5.31–5.52 | +60.8% | +196.5% |
| COPY → staging → final | + UPSERT | 7.29 | 68,552 | 7.16–7.61 | +36.4% | +304.4% |

#### Order item

| Method | Configuration | Median s | Rows/s | Range s | Δ previous | Δ base |
|---|---|---:|---:|---:|---:|---:|
| execute_values | Base | 35.94 | 48,705 | 34.74–36.49 | — | — |
| execute_values | + CHECK | 37.20 | 47,057 | 35.91–38.15 | +3.5% | +3.5% |
| execute_values | + PK / UNIQUE | 43.23 | 40,494 | 40.82–49.13 | +16.2% | +20.3% |
| execute_values | + FK | 59.24 | 29,553 | 56.03–63.87 | +37.0% | +64.8% |
| execute_values | + UPSERT | 66.87 | 26,179 | 63.38–70.71 | +12.9% | +86.0% |
| COPY → staging → final | Base | 6.93 | 252,601 | 6.80–7.02 | — | — |
| COPY → staging → final | + CHECK | 7.50 | 233,419 | 7.30–7.79 | +8.2% | +8.2% |
| COPY → staging → final | + PK / UNIQUE | 13.56 | 129,058 | 13.17–14.06 | +80.9% | +95.7% |
| COPY → staging → final | + FK | 28.56 | 61,294 | 27.75–29.39 | +110.6% | +312.1% |
| COPY → staging → final | + UPSERT | 37.73 | 46,402 | 35.83–38.08 | +32.1% | +444.4% |

PK/UNIQUE and foreign-key checks are the largest contributors. FK checks add 110.6% over the PK/UNIQUE case for staged order-item loading.

### Full-schema method comparison

CHECK, PK/UNIQUE, FK, and UPSERT enabled; one excluded warm-up and five randomized measured runs.

| Table | Method | Median s | Median rows/s | Range s |
|---|---|---:|---:|---:|
| order | execute_values | 14.38 | 34,759 | 13.76–15.13 |
| order | COPY → staging → final | 7.29 | 68,570 | 6.94–7.31 |
| order_item | execute_values | 64.47 | 27,153 | 62.63–65.08 |
| order_item | COPY → staging → final | 35.05 | 49,947 | 34.68–36.00 |

COPY through staging was 1.97× faster for order and 1.84× faster for order-item under the full schema.
