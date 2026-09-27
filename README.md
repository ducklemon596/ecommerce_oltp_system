# E-commerce OLTP synthetic data pipeline

A deterministic Python generator and PostgreSQL loader for a realistic e-commerce OLTP dataset. The project is designed to exercise relational data generation, temporal integrity, transactional loading, recovery behavior, and large-file ingestion—not to model every e-commerce workflow.

## What it provides

- Generates nine related tables with Faker and a configurable seed.
- Writes small reference/dependent tables as CSV and streams large `order` and `order_item` data into paired part files.
- Creates PostgreSQL tables, constraints, audit columns, staging tables, and load checkpoints.
- Uses idempotent, checksum-protected loading with transactions, retries for large parts, and sequence synchronization.
- Includes unit tests for generator contracts and PostgreSQL integration tests for rollback, retry, checkpoint, and concurrency behavior.

## Data flow

```text
seed + configuration
        |
        v
reference/master generation -> validation -> reference CSV files
        |                                      |
        +--------------------------------------+ 
                                               v
                              streamed order + order_item part files
                                               |
                                               v
schema -> dependency-aware PostgreSQL loader -> final tables
```

See [generators/README.md](src/ecommerce_oltp_system/generators/README.md) and [loader/README.md](src/ecommerce_oltp_system/loader/README.md) for implementation-level guidance.

## Tables and relationships

| Area | Tables | Main relationships |
|---|---|---|
| Catalog | `brand`, `category`, `seller`, `product` | A product references one brand, category, and seller. Categories may have a parent category. |
| Customers | `customer` | An order references one customer. |
| Promotions | `promotion`, `promotion_product` | Promotion-product maps a promotion to a product. |
| Transactions | `order`, `order_item` | An order has items; each item references one product. |

All final tables use database-managed serial/identity primary keys, stable business/source codes, audit fields, and `loaded_at DEFAULT CURRENT_TIMESTAMP`. `order` is quoted in SQL because it is a reserved word.

## Repository layout

```text
src/ecommerce_oltp_system/
  generate.py                 # generation CLI
  load.py                     # loading CLI
  generators/
    pipeline.py               # end-to-end generation orchestration
    reference/                # master/dependent generation and validation
    orders/                   # streamed order generation and validation
  loader/
    pipeline.py               # schema-and-load orchestration
    db/                       # connection, schema, serial sequences
    checkpoint/               # checksum/checkpoint repository
    strategies/               # small-table and large-part loaders
```

## Requirements and installation

- Python 3.12 or later
- PostgreSQL available to the machine running the loader
- [uv](https://docs.astral.sh/uv/) (recommended)

```bash
uv sync
```

The project declares `Faker` and `psycopg2-binary` in `pyproject.toml`; `uv sync` installs them.

## Database configuration

Create a local configuration file. It is ignored by Git.

```bash
cp database.ini.example database.ini
```

Edit the `[postgresql]` values in `database.ini`:

```ini
[postgresql]
host=localhost
port=5432
database=ecommerce_oltp
user=postgres
password=change-me
```

The loader requires `host`, `database`, `user`, and `password`; `port` is optional. Use `--config` and `--section` to select a different file or INI section.

## Commands

| Command | Purpose |
|---|---|
| `uv run generate` | Generate all tables and CSV files |
| `uv run load` | Create the schema and load CSV files into PostgreSQL |

These are the only public console entry points.

## Generate the dataset

Generate the complete default dataset (5,000,000 orders, 100,000 orders per part):

```bash
uv run generate
```

For a smaller development run:

```bash
uv run generate --orders 1000 --orders-per-file 500
```

Reference tables only:

```bash
uv run generate --base-only
```

Generated files are written below `data/` by default:

```text
data/brand.csv                  data/product.csv
data/category.csv               data/promotion.csv
data/seller.csv                 data/promotion_product.csv
data/customer.csv
data/orders/order_part_0001.csv
data/order_items/order_item_part_0001.csv
```

## Load the dataset

Create the schema if necessary, then load all files:

```bash
uv run load
```

Useful options:

```bash
uv run load --schema-only
uv run load --skip-schema --data-dir data
uv run load --config database.ini --section postgresql
```

### Loading model

| Table group | Strategy | Transaction boundary |
|---|---|---|
| `brand` through `promotion_product` | Parameterized batched `execute_values` UPSERT | One CSV file / table |
| `order`, `order_item` | `COPY` CSV → unlogged staging → final-table UPSERT → staging truncate | One generated part file |

The loader processes parents before children and each order part before its corresponding item part. It preserves CSV row order because generated numeric foreign keys rely on predictable PostgreSQL IDs.

## Reliability behavior

- **UPSERT:** uses each table's stable code key (`*_code` / `promotion_product_code`) rather than a generated primary key.
- **Checkpoint:** after a successful file load, a `(table_name, file_name)` row with row count and SHA-256 checksum is inserted in the same transaction as the data.
- **Restart:** an unchanged completed file is skipped; a filename with changed contents raises a checksum mismatch; an absent checkpoint loads or retries the whole file.
- **Rollback:** a failing row rolls back all data and the checkpoint for that file or part. Large `order`/`order_item` parts retry once; small files do not have an automatic retry loop.
- **Sequences:** before loading, the target serial sequence is aligned to the actual maximum key. This prevents a rolled-back attempt from shifting expected generated IDs.
- **Concurrency:** the loader takes an exclusive lock on the final target table and rechecks the checkpoint after the lock, preventing two concurrent attempts from both applying the same file.

This design assumes a clean or compatible database: parent IDs must match the generated one-based file positions. The loader intentionally does not remap foreign keys by business code.

## Testing

```bash
uv run python -m unittest discover -s tests -q
```

- `tests/unit/` checks deterministic generation, contracts, temporal rules, CSV headers, validation-before-write, and order/item calculations.
- `tests/integration/` uses an isolated PostgreSQL schema to test schema creation, checkpoints, rollback, retry, constraints, staging cleanup, and concurrent same-file loads.
- `tests/performance/` is reserved for manual benchmarks and is excluded from normal discovery.

## Benchmark snapshot

Historical manual measurements used 500,000 orders and 1,750,656 order items, with five measured runs after warm-up. Under the full schema (checks, PK/UNIQUE, FKs, and UPSERT), `COPY → staging → final` outperformed `execute_values`:

| Table | `execute_values` median | COPY/staging median | Relative improvement |
|---|---:|---:|---:|
| `order` | 14.38 s / 34,759 rows/s | 7.29 s / 68,570 rows/s | 1.97× |
| `order_item` | 64.47 s / 27,153 rows/s | 35.05 s / 49,947 rows/s | 1.84× |

PK/UNIQUE indexes and foreign-key checks were the largest observed costs, especially for `order_item`. These are environment-specific measurements, not production capacity guarantees.

## Design decisions and trade-offs

- CSV keeps generation inspectable and supports streaming, at the cost of more disk I/O than a direct database generator.
- Staging plus COPY is used only where volume warrants the added path; smaller tables stay simple and debuggable with parameterized UPSERTs.
- File-level checkpoints favor straightforward recovery over fine-grained resume or additional metadata tables.
- Expected positional IDs avoid pre-generating database primary keys in Python, but require controlled load order and a compatible database state.

## Current limitations and next steps

- No order or item ID remapping for an already-populated database.
- No checkpoint pruning, partial-file resume, parallel loading, or batching/checkpoint tuning controls.
- No production benchmark harness is currently committed; benchmark values above are recorded manual results.
- `stock_qty` is a snapshot attribute; generation does not decrement it across orders.

Possible next steps include a repeatable benchmark runner, configurable retry policy, `COPY` support for additional tables, explicit database migration tooling, and ID/business-key remapping for integration with pre-existing data.
