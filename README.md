## Synthetic-data generator (first version)

This version generates and validates `brand`, `category`, `seller`, `product`,
`customer`, `promotion`, and `promotion_product`, then writes each table to CSV.
It does not connect to PostgreSQL.

Run one deterministic generation session:

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
```

Run the tests:

```bash
uv run python -m unittest discover -s tests
```

The generator uses seed `42`. Stable business keys use the forms `BRD-00001`,
`CAT-00001`, `SEL-00001`, `PRD-000001`, and `PRO-00001`. PostgreSQL-managed
primary keys are absent from the files.

Integer foreign keys are based on expected future PostgreSQL IDs:

- `category.parent_category_id` points to expected category IDs `1..5`.
- Product `brand_id`, `category_id`, and `seller_id` point to the deterministic
  row positions of their parent files. Product categories use only IDs `6..25`.
- Promotion-product `promotion_id` and `product_id` point to deterministic row
  positions in `promotion.csv` and `product.csv`.

This assumption is valid only when a future loader uses clean empty tables,
starts every sequence at 1, preserves CSV row order, loads parent tables first,
and inserts every parent row without gaps. Partial retries or loading into
nonempty tables require a later ID-resolution design.

All records include audit columns. `created_by` is `faker_batch`; update and
deletion fields are empty; `is_deleted` is false. `loaded_at` stays empty because
it represents the real PostgreSQL load time, which does not exist at this stage.
