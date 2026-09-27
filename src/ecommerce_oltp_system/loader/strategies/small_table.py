"""Transactional ``execute_values`` loading for reference and medium tables."""

from __future__ import annotations

import csv
from pathlib import Path

from psycopg2 import sql as pg_sql
from psycopg2.extensions import connection, cursor
from psycopg2.extras import execute_values

from ..checkpoint.repository import file_checksum, read_checkpoint, read_checkpoint_in_transaction, write_checkpoint
from ..config import UPSERT_BATCH_SIZE
from ..exceptions import CheckpointMismatchError, TableLoadError
from ..models import LoadOutcome, TableLoad
from ..parsing import parse_value, validate_header
from ..db.sequences import synchronize_sequence


def load_table(database: connection, config: TableLoad, csv_path: Path) -> LoadOutcome:
    """Load one small/medium reference CSV using bounded ``execute_values`` batches.

    This strategy is used for brand, category, seller, customer, product,
    promotion, and promotion-product files. ``config`` provides the table's CSV
    contract, stable conflict key, and sequence requirements; ``csv_path`` is
    the single source file. It returns a loaded or checkpoint-skipped outcome.

    Header validation, type conversion, serial sequence synchronization, all
    UPSERT batches, and checkpoint insertion share one transaction. Any parsing,
    constraint, or checkpoint error rolls back the entire file; unchanged
    completed files are skipped after checksum validation.
    """
    checksum = file_checksum(csv_path)
    checkpoint = read_checkpoint(database, config.table, csv_path.name)
    if checkpoint:
        return _checkpoint_outcome(config.table, csv_path, checksum, checkpoint)

    row_number = 0
    try:
        with database.cursor() as db_cursor:
            # Serialise same-file loads before re-checking the checkpoint.
            db_cursor.execute(pg_sql.SQL("LOCK TABLE {} IN EXCLUSIVE MODE").format(pg_sql.Identifier(config.table)))
            checkpoint = read_checkpoint_in_transaction(db_cursor, config.table, csv_path.name)
            if checkpoint:
                outcome = _checkpoint_outcome(config.table, csv_path, checksum, checkpoint, after_lock=True)
                database.commit()
                return outcome

            synchronize_sequence(db_cursor, config)
            statement = upsert_statement(config)
            with csv_path.open("r", encoding="utf-8", newline="") as source:
                reader = csv.DictReader(source)
                validate_header(reader.fieldnames, config, csv_path)
                batch: list[tuple[int, tuple[object, ...]]] = []
                for row_number, row in enumerate(reader, start=1):
                    if row["loaded_at"]:
                        raise ValueError("loaded_at must be empty so PostgreSQL can set it")
                    values = tuple(parse_value(column, row[column]) for column in config.columns)
                    batch.append((row_number, values))
                    if len(batch) == UPSERT_BATCH_SIZE:
                        upsert_batch(db_cursor, statement, config, batch)
                        batch.clear()
                if batch:
                    upsert_batch(db_cursor, statement, config, batch)
            write_checkpoint(db_cursor, config.table, csv_path.name, checksum, row_number)
        database.commit()
        print(f"LOADED {config.table} {csv_path.name}: {row_number:,} rows.")
        return LoadOutcome(row_number)
    except Exception as exc:
        database.rollback()
        location = f" at data row {row_number}" if row_number else ""
        raise TableLoadError(f"Rolled back {config.table} load from {csv_path}{location}: {exc}") from exc


def _checkpoint_outcome(table: str, csv_path: Path, checksum: str, checkpoint, *, after_lock: bool = False) -> LoadOutcome:
    """Validate an existing checkpoint and return its idempotent skip result."""
    if checkpoint[0] != checksum:
        raise CheckpointMismatchError(f"CHECKSUM MISMATCH for {table} {csv_path.name}: source file changed")
    location = " after lock" if after_lock else ""
    print(f"SKIPPED {table} {csv_path.name} (checkpoint{location}).")
    return LoadOutcome(checkpoint[1], skipped=True)


def upsert_batch(db_cursor: cursor, statement: pg_sql.Composed, config: TableLoad, batch: list[tuple[int, tuple[object, ...]]]) -> None:
    """UPSERT one bounded CSV batch and validate configured positional IDs."""
    generated_rows = execute_values(db_cursor, statement, [values for _, values in batch], page_size=len(batch), fetch=True)
    if len(generated_rows) != len(batch):
        raise ValueError(f"Expected {len(batch)} generated IDs, received {len(generated_rows)}")
    if config.requires_positional_ids:
        for (row_number, _), (generated_id,) in zip(batch, generated_rows):
            if generated_id != row_number:
                raise ValueError(f"{config.primary_key} {generated_id} does not match expected CSV position {row_number}")


def upsert_statement(config: TableLoad) -> pg_sql.Composed:
    """Build the stable-business-key UPSERT for one reference table."""
    update_columns = [column for column in config.columns if column not in config.conflict_columns]
    assignments = [
        pg_sql.SQL("{} = EXCLUDED.{}").format(pg_sql.Identifier(column), pg_sql.Identifier(column))
        for column in update_columns
    ]
    assignments.append(pg_sql.SQL("loaded_at = CURRENT_TIMESTAMP"))
    return pg_sql.SQL(
        """
        INSERT INTO {table} ({columns})
        VALUES %s
        ON CONFLICT ({conflict_columns})
        DO UPDATE SET {assignments}
        RETURNING {primary_key}
        """
    ).format(
        table=pg_sql.Identifier(config.table),
        columns=pg_sql.SQL(", ").join(map(pg_sql.Identifier, config.columns)),
        conflict_columns=pg_sql.SQL(", ").join(map(pg_sql.Identifier, config.conflict_columns)),
        assignments=pg_sql.SQL(", ").join(assignments),
        primary_key=pg_sql.Identifier(config.primary_key),
    )
