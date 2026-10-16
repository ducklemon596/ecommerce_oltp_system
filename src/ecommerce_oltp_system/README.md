# Application package

Connects synthetic generation, PostgreSQL loading, and SQL-backed report exports
through one application CLI. Business SQL stays in the [database package](../../database/README.md).

## File overview

| File or package | Purpose |
|---|---|
| [cli.py](cli.py) | Routes `ecommerce generate`, `init-db`, `load`, and `report` |
| [generate.py](generate.py) | Parses generation options and selects full, reference-only, or orders-only mode |
| [reporting.py](reporting.py) | Maps report names to deployed SQL functions, binds parameters, and saves bounded CSV exports |
| [generators/](generators/README.md) | Data generation, validation, models, and CSV writing; no database connections |
| [loader/](loader/README.md) | Schema setup, transactions, loading strategies, checkpoints, and sequence synchronization |
| `__init__.py` | Python package marker |

## Usage and dependencies

From the repository root:

```bash
uv run ecommerce --help
uv run report list
```

The CLI delegates to the packages rather than implementing their workflows again.
Reporting reuses the loader's INI configuration parser but uses read-only database
transactions. There is no separate shared-utilities package.

See the [project README](../../README.md) for installation and complete commands.
