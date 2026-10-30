# PostgreSQL integration tests

Checks real transactions, constraints, checkpoints, and reporting semantics with
small fixtures in disposable schemas. It does not reload the large dataset.

## File overview

| File | Purpose |
|---|---|
| [test_loader_checkpoints.py](test_loader_checkpoints.py) | File/part loading, checksum mismatch, rollback/retry, constraints, UPSERT, sequence repair, staging cleanup, and concurrent loads |
| [test_reporting.py](test_reporting.py) | Function/standalone equivalence and column/order contracts, filters, deletion scope, date boundaries, and ranking ties |
| [test_cli_smoke.py](test_cli_smoke.py) | Public generation/load/setup/category-export flow, index inventory and checkpoint resume |

## Usage and safety

Run from the repository root with a separate INI for a dedicated test database.
`ECOMMERCE_TEST_CONFIG` selects it without changing application configuration.
The CLI's `--config` option does not apply to unittest.

```bash
ECOMMERCE_TEST_CONFIG=database-test.ini ECOMMERCE_TEST_STRICT=1 uv run python -m unittest discover -s tests/integration -v
# Run only the repeatable demo check:
ECOMMERCE_TEST_CONFIG=database-test.ini ECOMMERCE_TEST_STRICT=1 uv run python -m unittest tests.integration.test_cli_smoke -v
```

The loader tests commit their temporary-schema setup and remove it on teardown.
Reporting fixtures and definitions remain in a transaction that is rolled back.
Production application tables/functions are not the test targets, but creating
temporary schemas still changes the configured database's catalogs. Use a separate
test database, not a busy production database. A force-killed loader-test process
can leave a `loader_test_*` schema; verify ownership before manually removing it.

A reachable server and CREATE/DROP SCHEMA privileges are required. Strict mode
fails if explicit config is missing or PostgreSQL is unavailable; CI enables it.
Without strict mode, unavailable connections can skip tests, and older fixture
tests still default to `database.ini`. The CLI smoke always requires explicit test
configuration. Skips are not evidence of a successful DB test.
See the [test guide](../README.md) for database-free tests and shared helpers.

## What the smoke verifies

The smoke invokes the installed `ecommerce` entrypoint, generates 40 orders in two
paired parts, loads unchanged SQL/functions and C1+C2, and verifies all 25 mandatory
PK/UNIQUE indexes plus exactly those two optional indexes. It exports each category
twice with a two-row cap, checks SQL-defined headers and unique filenames, and
repeats the load to confirm order/item/checkpoint counts stay unchanged.

An actual run with seed 42 and PostgreSQL 16 produced this verification line:

```text
CLI smoke verified: 40 orders, 137 items, 11 checkpoints; 25 mandatory + C1/C2 indexes; 24 bounded CSVs; repeat-load counts unchanged.
```

This is a functional result, not a benchmark. Reference tables keep their normal
small-table sizes. CSVs, credentials and exports live in a temporary directory.
The smoke creates a unique `cli_smoke_*` schema, sets child connections' search
path to that schema alone, and drops only that schema on cleanup. Cleanup errors
fail the test. A force-killed process can leave its own schema behind; verify
ownership before removing it manually.
