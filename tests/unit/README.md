# Unit and contract tests

Fast tests using temporary CSV directories and mocked database calls. No running
PostgreSQL instance or production-size generation is required.

## File overview

| File | Purpose |
|---|---|
| [test_generator.py](test_generator.py) | Reference counts, deterministic seeds, temporal validation, and database-managed PK omission |
| [test_generation_contracts.py](test_generation_contracts.py) | Streamed headers, cross-part code continuity, timestamp/calculation rules, and validation-before-write |
| [test_report_cli.py](test_report_cli.py) | Parameter parsing, report selection, read-only calls, CSV exports, truncation, cleanup, and generation-mode dispatch |
| [test_reporting_sql.py](test_reporting_sql.py) | Function/standalone SQL agreement, packaged DDL consistency, console scripts, and CLI forwarding |

## Usage and dependencies

```bash
uv run python -m unittest discover -s tests/unit -v
```

The tests reuse production generators/validators and
[reporting_support.py](../reporting_support.py), rather than reimplementing their
business logic. See the [test guide](../README.md) for PostgreSQL coverage.
