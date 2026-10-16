# File-loading strategies

Implements the two transaction paths selected by the
[dependency-aware pipeline](../pipeline.py).

## File overview

| File | Tables | Purpose |
|---|---|---|
| [small_table.py](small_table.py) | Seven reference/dependent tables | Parse CSV values and execute bounded, parameterized UPSERT batches in one file transaction |
| [large_part.py](large_part.py) | `order`, `order_item` | COPY each part into staging, UPSERT ordered rows into the final table, validate order IDs, and clean staging |

## Transaction contract

Both paths lock the final table, recheck the checkpoint, synchronize its sequence,
apply all rows, and insert the checkpoint before commit. Any row/checkpoint error
rolls back that file's data. Completed earlier files remain committed.

The small-table path has no automatic retry loop. Large parts allow two attempts,
each a complete new transaction; staging is cleared before COPY and after UPSERT.
Stable business codes—not SERIAL primary keys—are the conflict targets.

Table metadata, batches, and attempt counts come from [config.py](../config.py).
Both paths reuse [database support](../db/README.md) and the
[checkpoint repository](../checkpoint/README.md).

## Usage

```bash
uv run ecommerce load --data-dir data --config database.ini
```

Do not call individual strategies out of dependency order. See the
[loader guide](../README.md) for file layout, ID assumptions, and recovery details.
