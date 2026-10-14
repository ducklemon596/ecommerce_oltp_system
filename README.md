# E-commerce OLTP: generation, loading, reporting, and SQL optimization

A Python/Faker and PostgreSQL project covering database design, deterministic
synthetic data, reliable file loading, parameterized reporting, and measured SQL
optimization. The dataset spans January–May 2025: **5 million orders and roughly
17.5 million order items**, plus catalog, customer, seller, and promotion data.

## Architecture

```text
PostgreSQL schema and constraints
        ↓
seeded generation → validation → CSV reference tables + streamed order/item parts
        ↓
transactional loading → staging/COPY or batched UPSERT → checkpoints
        ↓
12 reporting functions → execution plans → benchmark evidence → index decisions
```

Products reference brands, categories, and sellers; orders reference customers;
items connect orders to products. Promotion-product mappings connect promotions
to the catalog. Database-managed PKs, business-key uniqueness, FKs, CHECKs, and
audit columns protect the nine final tables.

## Start locally

Requirements: Python 3.12+, PostgreSQL 16, Docker Compose for the supplied
database setup, and [uv](https://docs.astral.sh/uv/) for dependency installation.

```bash
uv sync
cp database.ini.example database.ini
docker compose up -d
```

Edit the ignored `database.ini` for your connection. Local defaults:
`localhost:5432`, database `ecommerce_oltp`, user/password `postgres`.
Compose reuses the existing external PostgreSQL volume named in
`docker-compose.yml`; an already populated volume retains its data. Avoid
starting another PostgreSQL container against that volume simultaneously.

pgAdmin: [localhost:5050](http://localhost:5050), login
`admin@example.com` / `admin`. Register PostgreSQL using host `postgres`,
port `5432`, and the database credentials above.

## Generate and load

These are the only two public console commands:

```bash
uv run generate                                 # complete configured dataset
uv run generate --orders 1000 --orders-per-file 500
uv run generate --base-only                      # reference tables only
uv run load                                     # schema + dependency-ordered load
```

Small/medium files use batched UPSERT; each order/item part uses
`COPY → staging → final UPSERT`. Each file is one transaction, including its
SHA-256 checkpoint. A matching checkpoint skips a completed file; changed
contents fail clearly. Failed loads roll back data/checkpoints, and retries
synchronize sequences to stored PK maxima. Parents load before dependents.

Generation streams large tables and validates before final file writes. Expected
positional FK IDs assume predictable database allocation; this is a deliberate
benchmark simplification. See the [generator](src/ecommerce_oltp_system/generators/README.md)
and [loader](src/ecommerce_oltp_system/loader/README.md) guides for limits and options.

## Reporting

[functions.sql](database/reporting/functions.sql) contains the 12 canonical
functions covering all 13 original requirements. Public dynamic signatures,
half-open date windows, NULL/empty-array filters, soft deletion, and order-versus-
item revenue semantics are preserved.

Install functions after loading the schema; using the supplied container:

```bash
docker exec -i ecommerce-postgres psql -U postgres -d ecommerce_oltp \
  -v ON_ERROR_STOP=1 -1 < database/reporting/functions.sql
```

Run examples from [examples.sql](database/reporting/examples.sql).
The [function catalog and requirements mapping](database/reporting/README.md)
explain each report and the workload-driven index recommendations.

## Optimization evidence

The [main SQL optimization report](reports/sql_optimization/README.md) compares
original SQL → rewritten SQL → rewritten SQL with four additional indexes,
using one warm-up plus five measured `EXPLAIN (ANALYZE, BUFFERS)` runs per case.

- SQL rewrites improved key broad aggregates about **2.0–2.8×**.
- Product lookup improved about **73×** with the index set.
- Highest-value lookup fell from **682 ms to 0.041 ms**.
- The added index set cost about **2.28 GiB**, with approximately **23% order**
  and **10% item** INSERT-time overhead in the isolated write experiment.
- Broad scans do not uniformly benefit; a seller summary regressed with indexes.

The [historical dynamic-report benchmark](reports/dynamic_reports/README.md)
also records a top-brand SQL regression. Its archived candidate differs from the
current canonical SQL; historical timings are not new-function performance claims.
All four approved definitions remain in [indexes.sql](database/indexes.sql).
The date index remains provisional pending an individual-contribution experiment.

## Repository map

```text
src/ecommerce_oltp_system/    generators/, loader/, generate.py, load.py
database/                   schema.sql, indexes.sql, reporting/{functions,examples}.sql
benchmarks/                 cases.json and preserved original/rewritten SQL
scripts/                    benchmark runners, source verification, snapshots
reports/                    sql_optimization/, dynamic_reports/, data_validation/
tests/                      unit/, integration/, performance/
experiments/partitioning/    undeployed migration proposal and comparison utility
docs/                       course assignment, cleanup inventory and provenance
data/                       generated datasets (ignored)
```

`database/schema.sql` links to the single packaged schema resource, so SQL users
and installed loaders share the same DDL. Generation/loading modules and the
existing schema constraints remain unchanged by repository cleanup.

## Validate and reproduce

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Integration tests use isolated PostgreSQL schemas. Large benchmarks are manual
and excluded from normal tests. Workloads, measured-run counts, filters, seeds,
and representative-plan choices live in [cases.json](benchmarks/cases.json).
[Benchmark instructions](benchmarks/README.md) explain isolated clones and stable
`latest/` outputs that are replaced on subsequent runs. Frozen historical reports
require explicit `--overwrite`; restructuring did not rerun them.

Partitioning is [experimental and outstanding](experiments/partitioning/README.md),
not deployed. There are no materialized summaries or production partition
migrations. Next useful experiments are date-index ablation and selective versus
broad tests of the consolidated top-brand function.
