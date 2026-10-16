# PostgreSQL integration tests

Checks real transactions, constraints, checkpoints, and reporting semantics with
small fixtures in disposable schemas. It does not reload the large dataset.

## File overview

| File | Purpose |
|---|---|
| [test_loader_checkpoints.py](test_loader_checkpoints.py) | File/part loading, checksum mismatch, rollback/retry, constraints, UPSERT, sequence repair, staging cleanup, and concurrent loads |
| [test_reporting.py](test_reporting.py) | Function/standalone equivalence and column/order contracts, filters, deletion scope, date boundaries, and ranking ties |

## Usage and safety

Run from the repository root after configuring `database.ini` for a dedicated test
database. Tests use this file directly; the CLI's `--config` option does not apply.

```bash
uv run python -m unittest discover -s tests/integration -v
```

The loader tests commit their temporary-schema setup and remove it on teardown.
Reporting fixtures and definitions remain in a transaction that is rolled back.
Production application tables/functions are not the test targets, but creating
temporary schemas still changes the configured database's catalogs. Use a separate
test database, not a busy production database. A force-killed loader-test process
can leave a `loader_test_*` schema; verify ownership before manually removing it.

A reachable server and CREATE/DROP SCHEMA privileges are required. Some connection
failures skip integration classes; skips are not evidence of a successful DB test.
See the [test guide](../README.md) for database-free tests and shared helpers.
