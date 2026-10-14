# Loader package

The loader creates the PostgreSQL schema and applies generated CSV files safely in dependency order. It owns database connections, transactions, checkpoints, retries, sequence alignment, and loading strategies; it does not generate synthetic data.

For setup and the complete workflow, see the [root README](../../../README.md). Generator details are in [../generators/README.md](../generators/README.md).

## End-to-end load flow

```text
connect using database.ini
  -> apply schema.sql (unless --skip-schema)
  -> load reference/dependent CSV files
  -> for each part: load order, then matching order_item
  -> report row counts and elapsed time
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

Before every load transaction, the loader sets the target serial sequence to the actual maximum primary key. PostgreSQL sequences advance even when a transaction rolls back; this step preserves the generator's positional-ID assumption after a retry.

An exclusive lock on the final table and a second checkpoint check after acquiring that lock prevent concurrent processes from double-loading the same file. Staging is truncated before COPY and after the final UPSERT, so stale rows cannot affect the next part.

## Run it

Use the single loading entry point:

```bash
uv run load
```

```bash
cp database.ini.example database.ini
# edit credentials
```

Useful variants:

```bash
uv run load --schema-only
uv run load --skip-schema --data-dir data
uv run load --config database.ini --section postgresql
```

## Failure expectations

A file/table is the recovery unit for small tables; a part file is the recovery unit for `order` and `order_item`. Previously committed files remain committed when a later unit fails. Restart the same command after correcting the cause: matching completed files skip, while an uncheckpointed failed unit loads again.

A changed file under an existing completed filename is deliberately rejected. Rename/regenerate consistently or resolve the checkpoint intentionally; the loader does not silently merge changed source contents.

## Benchmark conclusion

Recorded manual benchmarks with full final-table constraints found `COPY → staging → final` about 1.97× faster than `execute_values` for orders and 1.84× faster for order items. PK/UNIQUE indexes and FK checks contributed most of the observed overhead. These results justify the two-strategy design but are hardware- and configuration-dependent.

## Main components

| Location | Responsibility |
|---|---|
| `pipeline.py` | CLI and dependency-aware end-to-end orchestration |
| `config.py`, `models.py`, `exceptions.py` | Table metadata, result contracts, and load errors |
| `db/connection.py` | INI configuration parsing |
| `db/schema.py` | Applies packaged SQL schema |
| `db/sequences.py` | Serial synchronization before loads/retries |
| `checkpoint/repository.py` | SHA-256 and transactional checkpoint persistence |
| `strategies/small_table.py` | Batched UPSERT strategy |
| `strategies/large_part.py` | COPY/staging/UPSERT/retry strategy |
| `parsing.py` | CSV header and PostgreSQL value conversion |
| `sql/schema.sql` | Single packaged DDL resource; also exposed by [database/schema.sql](../../../database/schema.sql) for SQL users |
