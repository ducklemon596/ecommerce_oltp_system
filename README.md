# PostgreSQL E-commerce OLTP & Reporting

A reproducible e-commerce data platform for studying relational integrity,
recoverable bulk ingestion, and SQL performance at **22.5 million records**.
It generates nine related tables, loads them into PostgreSQL with transactional
checkpoints, and exposes 12 parameterized business reports through a uv-managed CLI.

## What the project demonstrates

- Deterministic Faker generation with relational, temporal, monetary, and unique-key validation.
- Bounded-memory generation of 5 million orders and approximately 17.5 million items.
- Batched UPSERT and COPY/staging loading, including rollback, retry, checksum verification, and sequence repair.
- Reporting functions with explicit revenue attribution, date/filter semantics, and automatic CSV exports.
- Measured SQL/index trade-offs, including regressions—not just successful optimizations.

## Tech stack

| Component | Role |
|---|---|
| Python 3.12+ / Faker | Seeded synthetic data generation and validation |
| PostgreSQL | OLTP constraints, staging, checkpoints, reporting functions, and indexes |
| psycopg2 | Parameterized SQL, `execute_values`, and `COPY FROM STDIN` |
| uv | Locked dependencies and console commands |
| unittest | Generator/CLI contracts and PostgreSQL integration tests |
| Docker Compose / pgAdmin | Optional local database and SQL interface |

## System architecture

```text
uv run ecommerce generate
    → reference validation → reference CSVs
    → streamed order/item validation → paired CSV parts
                                               ↓
uv run ecommerce load → PostgreSQL final tables + checkpoints
                         ↑ COPY/staging for large parts
                                               ↓
database/reporting/functions.sql → uv run report → CSV exports
```

Generation does not connect to PostgreSQL. The loader owns database writes;
report execution calls deployed functions in read-only transactions. Application
DDL, performance-index DDL, and reporting SQL have separate deployment responsibilities.

## Quick start with uv

Run commands from the repository root. Install [uv](https://docs.astral.sh/uv/)
and make PostgreSQL available before loading.

```bash
uv sync
cp -n database.ini.example database.ini
uv run ecommerce --help
```

Configure `database.ini` for a **fresh development database**, not an unrelated
populated database. The loader creates tables, not the database itself. For example,
create `ecommerce_demo` with PostgreSQL tooling and use:

```bash
psql -h localhost -U postgres -d postgres -v ON_ERROR_STOP=1 \
  -c 'CREATE DATABASE ecommerce_demo;'
```

```ini
[postgresql]
host=localhost
port=5432
database=ecommerce_demo
user=postgres
password=change-me
```

Replace the username/password with your actual server credentials.

Create a small dataset in a fresh directory, then load it:

```bash
uv run ecommerce generate --output-dir data-sample --orders 1000 --orders-per-file 500
uv run ecommerce load --data-dir data-sample
```

Deploy reporting functions to that same database, then export a report:

```bash
psql -h localhost -U postgres -d ecommerce_demo -v ON_ERROR_STOP=1 -1 \
  -f database/reporting/functions.sql
uv run report monthly --start 2025-03-01 --end 2025-04-01
```

`database.ini` is ignored by Git. Loader/report commands also accept `--config`
and `--section`; keep real credentials local. See [SQL reporting](#sql-reporting)
for full/subset exports and index deployment.

### Optional Docker database and pgAdmin

```bash
docker compose up -d
docker compose ps
```

The supplied Compose file intentionally reuses an **existing external PostgreSQL
volume**. It does not create a portable empty database volume automatically. On a
different machine, create/select a local volume and set `volumes.postgres_data.name`
in [docker-compose.yml](docker-compose.yml) to that volume before starting. An empty
volume is a new database, not recovery of the existing dataset. Do not prune or
replace a populated volume merely to run the demo. Initialization environment
variables do not change credentials inside an already initialized volume.

Open pgAdmin at `http://localhost:5050`; development defaults are
`admin@example.com` / `admin`. Register PostgreSQL using host `postgres`, port
`5432`, and the credentials stored in that PostgreSQL volume. From the host machine,
`database.ini` uses `localhost:5432`. Override development passwords with local
environment variables as appropriate; do not expose these services publicly.

## Database schema and dataset

| Table | Evaluated rows | Relationships |
|---|---:|---|
| brand | 20 | Parent of products |
| category | 25 | Parent/child hierarchy; parent of products |
| seller | 50 | Parent of products |
| customer | 30,000 | Parent of orders |
| product | 3,000 | References brand, category, and seller |
| promotion | 30 | Parent of promotion-product assignments |
| promotion_product | 500 | References promotion and product |
| order | 5,000,000 | References customer |
| order_item | 17,500,990 | References order and product |

The observation window is January–May 2025. Final tables use database-managed
primary keys, stable unique business codes, CHECK/FK constraints, audit fields,
and `loaded_at DEFAULT CURRENT_TIMESTAMP`. `order` is quoted in SQL because it
is a reserved word. [database/schema.sql](database/schema.sql) links to the single
packaged DDL resource; see the [database guide](database/README.md).

## Generate the dataset

```bash
uv run ecommerce generate --output-dir data-full
uv run ecommerce generate --base-only --output-dir data-reference
```

Full generation defaults to seed 42, 5 million orders, and 100,000 orders per part.
Seven smaller tables are validated in memory; order/item records are validated
and streamed into matching `orders/` and `order_items/` part folders. Customer and
product creation must precede each order. Decimal arithmetic preserves subtotals
and order totals; `stock_qty` is a snapshot, not an inventory limit.

Always use a clean output directory: matching filenames are overwritten, but
surplus files from a larger run are not removed. Never overwrite completed
checkpointed inputs. Use `--data-dir` when loading a non-default output root.
The complete loader requires both reference CSVs and paired transactional parts;
`--base-only` is useful for inspecting reference generation, not a full load.

See the [generator guide](src/ecommerce_oltp_system/generators/README.md) for
determinism, output layout, and orders-only generation. The loading examples
below use the default `data/` root.

## Load the dataset

Create the schema if necessary, then load all files:

```bash
uv run ecommerce load
```

Useful options:

```bash
uv run ecommerce load --schema-only
uv run ecommerce load --skip-schema --data-dir data
uv run ecommerce load --config database.ini --section postgresql
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

## SQL reporting

The reporting layer covers monthly/daily revenue, seller performance and sales,
product/month revenue, global and within-brand rankings, status summaries, and
filtered order/item exports. Thirteen analytical requirements share **12 functions**.

```bash
uv run report list
uv run report                              # export all reports
uv run report monthly                      # export one
uv run report all --only monthly daily      # export a subset
uv run report seller-performance --categories 6,7 --brands 1,2
uv run report top-products-per-brand --sellers 1,2 --top 5
uv run ecommerce report monthly --help
```

Exports save automatically under `reports/results/`, with headers and unique
filenames. Defaults are March 2025 and at most 50 rows per report. `--output-dir`
changes the destination; `--limit` changes export size, not the business Top-N or
aggregation input. The longer `uv run ecommerce report ...` interface is equivalent.
The report runner never deploys SQL or modifies application records.

Important semantics:

- Full-order revenue and matching-item revenue are different measures. Seller
  revenue attributes only qualifying lines; multi-seller orders are not counted
  as distinct platform orders by summing seller counts.
- Windows are start-inclusive/end-exclusive. Item-date and parent-order-date
  reports deliberately differ; timestamp equality is not a schema invariant.
- Omitted/`null` ID filters disable filtering; `""` or `[]` matches nothing.
- Revenue includes all recorded statuses, including cancelled/returned orders;
  this is gross recorded revenue, not recognized/net revenue.

| SQL file | Purpose |
|---|---|
| [functions.sql](database/reporting/functions.sql) | Canonical callable reporting logic |
| [queries.sql](database/reporting/queries.sql) | Equivalent standalone SELECTs with example parameters |
| [original_queries.sql](database/reporting/original_queries.sql) | Original comparison SELECTs with documented provenance |
| [indexes.sql](database/indexes.sql) | Single source of approved performance-index definitions |

Deploy functions explicitly using the quick-start command or pgAdmin's Query Tool.
To inspect a standalone SELECT, prefix it with `EXPLAIN (ANALYZE, BUFFERS)`.
Execute [indexes.sql](database/indexes.sql) explicitly after loading; its standard
`CREATE INDEX` statements may run inside a transaction. The loader installs neither
reporting functions nor these performance indexes.

The [reporting catalog](database/reporting/README.md) specifies each function's
filters, deletion scope, revenue definition, and ranking tie-breaks.

## Benchmark snapshot

The [SQL optimization case study](reports/sql_optimization/README.md) evaluates
5 million orders and 17.5 million items using three consecutive warmups and seven
measured executions per query. Official primary B1/B2/FINAL results remain
separate from diagnostic controls and the historical C1+C2 selection stage.

| Finding | Historical evidence |
|---|---|
| March status summary, SQL rewrite | 141,685.865 → 1,301.510 ms |
| Equal-family workload, B2 → historical seven-index B3 | 32,742.020 → 27,487.573 ms |
| Portfolio recommendation | C1+C2, 826.602 MiB; not deployed by the report cleanup |
| Separate full-dataset loading study | Load then build: 456.742 s; indexes before load: 560.001 s |

The portfolio prioritizes sufficient interactive performance and OLTP maintenance
costs over maximum read speed. The [report](reports/sql_optimization/README.md)
explains the 26-session/104-SQL daily scenario, regressions, omitted indexes and
limitations. The [evidence guide](reports/sql_optimization/evidence/README.md)
provides the compact captures and integrity manifest. No benchmarks were rerun.

## Repository structure

```text
database/                         # DDL, approved indexes, reporting SQL
reports/sql_optimization/         # authoritative evaluation and compact evidence
src/ecommerce_oltp_system/
  cli.py, generate.py, reporting.py
  generators/                    # reference generation, order streaming, validation
  loader/                        # database support, checkpoints, loading strategies
tests/
  unit/                          # database-free contracts and CLI tests
  integration/                   # PostgreSQL fixture-schema tests
pyproject.toml, uv.lock           # project metadata, two console scripts, locked dependencies
docker-compose.yml               # PostgreSQL/pgAdmin with external-volume reuse
```

Start with the [application map](src/ecommerce_oltp_system/README.md),
[generator guide](src/ecommerce_oltp_system/generators/README.md),
[loader guide](src/ecommerce_oltp_system/loader/README.md), or
[report artifact guide](reports/README.md). Subpackage READMEs explain important
files and responsibilities without duplicating API documentation.

## Testing

Database-free tests:

```bash
uv run python -m unittest discover -s tests/unit -v
```

For the complete suite, first point `database.ini` at a dedicated test database:

```bash
uv run python -m unittest discover -s tests -q
```

Unit tests cover seeded generation, CSV contracts, validation, SQL consistency,
and report exports. Integration tests cover real constraints, rollback, retries,
checkpoints, concurrency, staging, and reporting semantics in disposable schemas.
They require CREATE/DROP SCHEMA privileges; they are not read-only database checks.
Performance experiments are manual and do not run in normal test discovery.
See [tests/README.md](tests/README.md) for scope and safety.

## Design decisions and limitations

- CSV makes generated data inspectable and supports bounded-memory streaming.
- File-level transactions/checkpoints simplify restart behavior without partial-file offsets.
- Expected positional IDs require a fresh or compatible target database; foreign
  keys are not remapped by business code for arbitrary populated databases.
- Generator validation precedes each record write, but streaming files are not
  atomically published and interrupted generation does not resume.
- No partitioning, checkpoint pruning, parallel loading, or configurable retry
  policy is implemented. Performance results are environment-specific.

Useful next evaluations are the seller/date query shape, broad aggregation spill,
and actual report frequency. Database migration tooling and source-key ID remapping
would address operational limitations; they are not implemented features.
