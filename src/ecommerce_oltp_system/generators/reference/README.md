# Reference and dependent data

Creates and validates the seven in-memory tables used before order streaming:
`brand`, `category`, `seller`, `customer`, `product`, `promotion`, and
`promotion_product`. It does not write files or connect to PostgreSQL.

## File overview

| File | Purpose |
|---|---|
| [generator.py](generator.py) | Faker records, stable source codes, audit defaults, catalog dependencies, and promotion assignments |
| [validation.py](validation.py) | Counts, unique keys, domain values, temporal rules, foreign-key positions, and promotion constraints |

## Usage and dependencies

[pipeline.py](../pipeline.py) initializes Python/Faker seeds, calls generators in
dependency order, and validates all reference tables before
[io.py](../io.py) writes them. Defaults and record contracts live in
[config.py](../config.py) and [models.py](../models.py).

```bash
uv run ecommerce generate --base-only --output-dir data-reference
```

Use a fresh output directory. For complete generation and positional-ID
assumptions, see the [generator guide](../README.md).
