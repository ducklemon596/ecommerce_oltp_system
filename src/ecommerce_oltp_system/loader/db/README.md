# Database support

Provides connection configuration, schema installation, and primary-key sequence
alignment for the [loading pipeline](../pipeline.py).

## File overview

| File | Purpose |
|---|---|
| [connection.py](connection.py) | Reads and validates PostgreSQL settings from an INI file; also reused by report exports |
| [schema.py](schema.py) | Executes the packaged DDL and commits it, or rolls it back on failure |
| [sequences.py](sequences.py) | Aligns a final table's SERIAL sequence with its real maximum key before insertion |

## Usage and transaction ownership

```bash
uv run ecommerce init-db --config database.ini
```

Schema application is a separate transaction before file loading. Sequence
synchronization runs inside each locked file-load transaction, including retries.
PostgreSQL sequence changes survive rollback; synchronization repairs the next
attempt rather than making sequences transactional.

The canonical [schema resource](../sql/README.md) creates final, staging, and
checkpoint tables, not performance indexes or reporting functions. See the
[loader guide](../README.md) for the complete flow and connection options.
