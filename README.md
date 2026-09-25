## Synthetic-data generator and PostgreSQL loader

This version generates and validates `brand`, `category`, `seller`, `product`,
`customer`, `promotion`, and `promotion_product`, writes each table to CSV, and
can create and load their PostgreSQL schema. A separate streaming benchmark
generates `order` and `order_item` CSV parts; PostgreSQL loading for those two
tables is intentionally not implemented yet.

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
primary keys are absent from the files.

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
then create the schema and load all seven files:

```bash
cp database.ini.example database.ini
# Update database.ini with your host, database, user, and password.
uv run ecommerce-load-data
```

The default section is `[postgresql]`; `port` is optional. The actual
`database.ini` is ignored by Git to protect credentials.

The schema is defined in `src/ecommerce_oltp_system/sql/schema.sql`. To create
only the tables, use `uv run ecommerce-load-data --schema-only`. To load into an
already-created schema, use `uv run ecommerce-load-data --skip-schema`. A custom
CSV directory can be supplied with `--data-dir`.

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
