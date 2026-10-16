# Test suite

Tests protect current generation, SQL semantics, CLI exports, and transactional
loading without generating the production-scale dataset.

## File overview

| Location | Purpose |
|---|---|
| [unit/](unit/README.md) | Database-free generation, CLI, CSV, and SQL contract tests |
| [integration/](integration/README.md) | PostgreSQL rollback/recovery/concurrency and reporting-semantic tests |
| [reporting_support.py](reporting_support.py) | Shared canonical-function parsing and literal SQL rendering for tests |
| `__init__.py` | Enables package imports and unittest discovery |

## Usage

Run the fast, database-free suite from the repository root:

```bash
uv run python -m unittest discover -s tests/unit -v
```

For the complete suite, point `database.ini` at a dedicated test database first:

```bash
uv run python -m unittest discover -s tests -v
```

Integration tests create/drop disposable schemas and need schema privileges.
Review the [integration guide](integration/README.md) before running them.
Performance experiments are manual and separate from test discovery; their
measurements live in the [canonical evaluation](../reports/sql_optimization/README.md).
