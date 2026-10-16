# PostgreSQL definitions

SQL interface for application schema setup, reporting, and workload indexes.
Database connection settings live in the local, ignored `database.ini`.

## File overview

| File or folder | Purpose |
|---|---|
| [schema.sql](schema.sql) | Symlink to the loader's canonical [packaged DDL](../src/ecommerce_oltp_system/loader/sql/schema.sql); final tables, constraints, staging, and checkpoints |
| [indexes.sql](indexes.sql) | Single source for the four approved partial composite performance indexes |
| [reporting/](reporting/README.md) | Parameterized functions, equivalent standalone SELECTs, original comparison SQL, and report semantics |

## Usage and deployment order

1. Create the database using PostgreSQL tooling and configure `database.ini`.
2. Run `uv run ecommerce init-db` or `uv run ecommerce load` to install application DDL.
3. Load the dataset in dependency order.
4. Deploy reporting functions in the same schema as the application tables.
5. If needed, execute each `indexes.sql` statement separately in autocommit mode.

`CREATE INDEX CONCURRENTLY` cannot execute inside a transaction block. Indexes and
reporting functions are not installed by the loader or report runner. For initial
bulk loads, the [benchmark evaluation](../reports/sql_optimization/README.md)
supports building performance indexes afterward; integrity indexes stay enabled.

Use [reporting/README.md](reporting/README.md) for function deployment, filters,
and standalone EXPLAIN usage. The [root README](../README.md#sql-reporting)
provides copy-paste commands. No partitioned-table migration is implemented.
