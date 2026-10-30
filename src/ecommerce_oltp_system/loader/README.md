# Loader package

The loader creates the PostgreSQL schema and applies generated CSV files safely in dependency order. It owns database connections, transactions, checkpoints, retries, sequence alignment, and loading strategies; it does not generate synthetic data.

For setup and the complete workflow, see the [root README](../../../README.md). Generator details are in [../generators/README.md](../generators/README.md).

## End-to-end load flow

```text
validate config, required files/paired parts, and requested setup SQL
  -> connect using database.ini
  -> apply schema.sql (unless --skip-schema)
  -> load reference/dependent CSV files
  -> for each part: load order, then matching order_item
  -> report row counts and elapsed time
  -> optionally install reporting functions/C1+C2 in a separate transaction
```

The schema includes final constrained tables, unlogged `staging_order` and `staging_order_item` tables, and the `load_checkpoint` table.

## Dependency order

```text
brand, category, seller, customer
  -> product
  -> promotion
  -> promotion_product
  -> order part N
  -> order_item part N
```

The order/item order is essential: generated `order_item.order_id` values are expected PostgreSQL IDs, not values supplied in the order CSV. CSV row order is retained during insertion.

## Loading strategies

### Small and medium tables

`brand`, `category`, `seller`, `customer`, `product`, `promotion`, and `promotion_product` use parameterized `execute_values` batches. Each source CSV is one transaction:

```text
BEGIN
  lock final table
  recheck checkpoint
  synchronize serial sequence
  validate CSV header and parse rows
  batched INSERT ... ON CONFLICT ... DO UPDATE
  insert checkpoint
COMMIT
```

The conflict key is the stable source/business code: `brand_code`, `category_code`, `seller_code`, `customer_code`, `product_code`, `promotion_code`, or `promotion_product_code`. Other schema uniqueness constraints, such as customer email/phone and the promotion-product pair, remain enforced by PostgreSQL.

### Large transactional tables

Each `order_part_*.csv` and corresponding `order_item_part_*.csv` uses one transaction through `COPY` and an unlogged staging table:

```text
BEGIN
  lock final table and recheck checkpoint
  synchronize serial sequence
  TRUNCATE staging
  validate header
  COPY CSV -> staging
  INSERT final SELECT staging ORDER BY staging_row_id
    ON CONFLICT (business_code) DO UPDATE
  TRUNCATE staging
  insert checkpoint
COMMIT
```

`order_code` and `order_item_code` are the UPSERT conflict keys. The order strategy verifies that generated `order_id` values still match `ORD-...` source positions. Final constraints—PKs, FKs, checks, and unique indexes—are applied on the final tables, not staging.

## Checkpoint and recovery behavior

A checkpoint stores `table_name`, `file_name`, SHA-256 checksum, row count, and completion time. It is inserted within the same transaction as the data load.

| Situation | Result |
|---|---|
| Checkpoint exists; checksum matches | `SKIPPED`; data is not applied again |
| Checkpoint exists; checksum differs | Clear checksum-mismatch failure |
| No checkpoint | Load the complete CSV or part |
| A row/constraint/COPY failure occurs | Roll back data, staging effects, and checkpoint for that unit |
| Large part fails | Retry the complete part once, then raise if it fails again |
| Small table fails | Roll back and raise; a later command invocation can retry it |

At the start of each locked load transaction, the loader sets the target serial sequence to the actual maximum primary key. PostgreSQL sequence changes survive rollback; synchronization on the next attempt preserves the generator's positional-ID assumption after a retry.

An exclusive lock on the final table and a second checkpoint check after acquiring that lock prevent concurrent processes from double-loading the same file. Staging is truncated before COPY and after the final UPSERT, so stale rows cannot affect the next part.

## Run it

Use the single loading entry point:

```bash
uv run ecommerce load
```

```bash
cp database.ini.example database.ini
# edit credentials
```

Useful variants:

```bash
uv run ecommerce init-db
uv run ecommerce load --skip-schema --data-dir data
uv run ecommerce load --config database.ini --section postgresql
```

Use `uv run ecommerce load` for loading and `uv run ecommerce init-db` for
initialization. Both commands delegate to the same pipeline and connection configuration.

## Failure expectations

A file/table is the recovery unit for small tables; a part file is the recovery unit for `order` and `order_item`. Previously committed files remain committed when a later unit fails. Restart the same command after correcting the cause: matching completed files skip, while an uncheckpointed failed unit loads again.

A changed file under an existing completed filename is deliberately rejected.
Restore the original input or use a fresh isolated database/dataset; do not delete
checkpoints or rename changed completed inputs to bypass validation.

If post-load setup fails, ingestion remains committed. Correct the cause and run
`ecommerce setup` with the same connection, SQL and index options. The CLI reports
this partial success explicitly. The [decision note](../../../docs/decisions/recoverable-load.md)
explains the transaction boundary and recovery trade-off.

## Performance evaluation

The [canonical evaluation](../../../reports/SQL_Optimization_README.md) measures
full-dataset loading with performance indexes built before or after ingestion.
It supports building those indexes after an initial bulk load while keeping
required integrity/UPSERT indexes enabled. Bare loading does not install optional
indexes. `load --indexes recommended` explicitly deploys functions and C1+C2 after
successful ingestion; `setup` exposes that operation separately. See the
[usage guide](../../../docs/usage/usage-guide.md). Measurements and their limitations
belong in the performance report, not here.

## File overview

| Location | Responsibility |
|---|---|
| [pipeline.py](pipeline.py) | CLI options, dependency-aware orchestration, paired parts, and timing output |
| [config.py](config.py) | Table/CSV metadata, stable conflict keys, type mappings, batch size, and retry count |
| [models.py](models.py) | Immutable table metadata and load/skip result contracts |
| [exceptions.py](exceptions.py) | Transaction failure and checkpoint mismatch errors |
| [parsing.py](parsing.py) | Exact CSV header checks and PostgreSQL value conversion |
| [db/](db/README.md) | INI configuration, packaged schema application, and sequence alignment |
| [checkpoint/](checkpoint/README.md) | SHA-256 file identity and transactional checkpoint persistence |
| [strategies/](strategies/README.md) | Small-table UPSERT and large-part COPY/staging transactions |
| [sql/](sql/README.md) | Single packaged DDL resource, also exposed by [database/schema.sql](../../../database/schema.sql) |
