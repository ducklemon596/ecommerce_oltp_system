# File checkpoints

Identifies completed CSV loads and makes restarts operate at the same granularity
as the loader's transactions: one reference CSV or one order/item part.

## File overview

| File | Purpose |
|---|---|
| [repository.py](repository.py) | Streams SHA-256 checksums and reads/writes `load_checkpoint` rows |

## Responsibilities and integration

Both [loading strategies](../strategies/README.md) compute the checksum before
loading, check for completion, then recheck after locking the final table.

| Checkpoint state | Action |
|---|---|
| Same table/filename and checksum | Skip the file |
| Same table/filename, different checksum | Reject changed input |
| No checkpoint | Load the entire file |

The repository writes the checkpoint through the caller's cursor; it never
commits it independently. Data and completion therefore commit or roll back
together. The preliminary read rolls back its implicit read transaction so the
load can begin cleanly. Concurrency locks belong to the loading strategies.

There are no row offsets or external state files. Restart with the same
`uv run ecommerce load` command; see the [loader guide](../README.md) for recovery
and positional-ID limitations.
