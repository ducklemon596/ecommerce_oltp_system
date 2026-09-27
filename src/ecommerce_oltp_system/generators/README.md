# Generator package

The generator creates a deterministic, relationally consistent CSV dataset for the e-commerce schema. It owns synthetic data creation and validation; it does not connect to PostgreSQL.

For project setup and the end-to-end workflow, see the [root README](../../../README.md). The loader is documented in [../loader/README.md](../loader/README.md).

## Generation flow

```text
seed/config
  -> reference and dependent records
  -> reference validation
  -> reference CSV files
  -> stream order + order_item records
  -> validate each order and its items
  -> paired order/item part files
```

The seven in-memory tables are `brand`, `category`, `seller`, `customer`, `product`, `promotion`, and `promotion_product`. They are generated and validated before their CSV files are written.

`order` and `order_item` are different: their target volumes are large, so they are generated one order at a time and written in paired files. The generator does not retain all orders or items in memory.

## Determinism and consistency

The default seed is `42`. With the same seed, package versions, configuration, and a clean output directory, generation keeps record and row order deterministic.

Important rules include:

- Brand/category/seller records are created in December 2024; parent categories predate children.
- Most products exist before the January–May 2025 observation window, with a smaller rollout through April.
- Customers are created during January–May 2025.
- An order uses only a customer and products created on or before its `order_date`.
- Order and item `created_at` values are at or shortly after the order date.
- Items use 2–5 distinct products, positive quantities and prices, and `subtotal = quantity × unit_price`.
- `order.total_amount` equals the sum of its item subtotals.
- Promotions, promotion-product links, audit defaults, enums, uniqueness, and temporal constraints are validated.

Reference data is validated as a complete dataset before any reference CSV is written. While streaming, each order and its item set is validated before its rows are appended to the current part files.

## Positional-ID assumption

CSV files deliberately omit database-managed primary keys. Numeric foreign keys in generated records represent the expected PostgreSQL IDs produced when parent CSVs load in their deterministic row order. For example, a product's `brand_id` is the expected row position of its brand, and an order item uses the expected future `order_id`.

This is why the loader must load tables in dependency order, preserve row order, and synchronize serial sequences before loading. It is not a general ID-remapping scheme for an arbitrary populated database.

## Output files

```text
data/
  brand.csv
  category.csv
  seller.csv
  customer.csv
  product.csv
  promotion.csv
  promotion_product.csv
  orders/
    order_part_0001.csv
    ...
  order_items/
    order_item_part_0001.csv
    ...
```

A part contains at most `ORDERS_PER_FILE` orders (100,000 by default). Its matching item part contains items only for that order range. Parting keeps memory bounded, limits retry/load scope, and makes large-file throughput measurable.

## Run it

Use the single generation entry point:

```bash
uv run generate
```

Full generation is the default behavior.

Smaller run:

```bash
uv run generate --orders 1000 --orders-per-file 500
```

Reference tables only:

```bash
uv run generate --base-only
```

The public `generate` command always starts with reference generation, then streams the order tables. Use `--seed`, `--orders`, and `--orders-per-file` to change the relevant settings. Use a clean output directory when comparing deterministic file output; generation overwrites matching names but does not delete old extra part files.

## Where to look

| Location | Responsibility |
|---|---|
| `config.py` | Seed, volumes, windows, domains, and distribution settings |
| `pipeline.py` | Full generation orchestration |
| `reference/generator.py` | Brand, category, seller, customer, product, and promotion generation |
| `reference/validation.py` | Reference/dependent validation |
| `orders/generator.py` | Streaming order and order-item generation and part-file writing |
| `orders/models.py` | Order CSV contracts and lightweight reference/statistics models |
| `orders/validation.py` | Per-order and per-item validation |
| `io.py` | Reference-table CSV serialization |
