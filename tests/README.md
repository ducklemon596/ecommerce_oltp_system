# Test suite

Tests protect current generation, SQL semantics, CLI exports, and transactional
loading without generating the production-scale dataset.

## File overview

| Location | Purpose |
|---|---|
| [unit/](unit/README.md) | Database-free generation, CLI, CSV, and SQL contract tests |
| [integration/](integration/README.md) | PostgreSQL rollback/recovery/concurrency and reporting-semantic tests |
| [reporting_support.py](reporting_support.py) | Shared canonical-function parsing and literal SQL rendering for tests |
| [integration_support.py](integration_support.py) | Dedicated test configuration and strict connection-failure policy |
| `__init__.py` | Enables package imports and unittest discovery |

## Usage

Run the fast, database-free suite from the repository root:

```bash
uv run python -m unittest discover -s tests/unit -v
```

For the complete suite, create a dedicated test INI and select it explicitly:

```bash
ECOMMERCE_TEST_CONFIG=database-test.ini ECOMMERCE_TEST_STRICT=1 uv run python -m unittest discover -s tests -v
```

This leaves application configuration unchanged. Strict mode requires the explicit
test config and fails on unavailable PostgreSQL instead of skipping DB checks.

Integration tests create/drop disposable schemas and need schema privileges.
Review the [integration guide](integration/README.md) before running them.
Performance experiments are manual and separate from test discovery; their
measurements live in the [canonical evaluation](../reports/SQL_Optimization_README.md).

The [CI workflow](../.github/workflows/verify.yml) has independent unit/build and
PostgreSQL integration jobs. Build validation installs the wheel outside the
checkout and checks packaged schema plus both CLI entrypoints. Reporting/index
SQL remains a checkout requirement; see the [usage guide](../docs/usage/usage-guide.md).
