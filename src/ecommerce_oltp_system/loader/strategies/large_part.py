"""COPY-to-staging transactions for high-volume order CSV parts."""

from __future__ import annotations

import csv
from pathlib import Path

from psycopg2 import sql as pg_sql
from psycopg2.extensions import connection, cursor

from ..checkpoint.repository import file_checksum, read_checkpoint, read_checkpoint_in_transaction, write_checkpoint
from ..config import PART_LOAD_ATTEMPTS
from ..exceptions import CheckpointMismatchError, TableLoadError
from ..models import LargeTableLoad, LoadOutcome
from ..db.sequences import synchronize_sequence


def load_large_part(database: connection, config: LargeTableLoad, csv_path: Path) -> LoadOutcome:
    """Load one ``order`` or ``order_item`` CSV part through COPY and staging.

    This is the large-table pipeline strategy invoked by :func:`loader.pipeline.load_all`.
    ``config`` selects the final/staging tables and conflict key; ``csv_path`` is
    one generated part. It returns a :class:`LoadOutcome`, including a skip when
    an unchanged checkpoint already exists.

    A failed attempt rolls back COPY, final-table UPSERT, staging truncation,
    checkpoint insertion, and sequence synchronization together. The function
    retries a rolled-back part up to ``PART_LOAD_ATTEMPTS``; successful attempts
    commit exactly one part-file transaction.
    """
    checksum = file_checksum(csv_path)
    checkpoint = read_checkpoint(database, config.table, csv_path.name)
    if checkpoint:
        return _checkpoint_outcome(config.table, csv_path, checksum, checkpoint)
    for attempt in range(1, PART_LOAD_ATTEMPTS + 1):
        try:
            return _load_large_part_transaction(database, config, csv_path, checksum)
        except TableLoadError:
            if attempt == PART_LOAD_ATTEMPTS:
                raise
            print(f"RETRY {config.table} {csv_path.name} (attempt {attempt + 1}/{PART_LOAD_ATTEMPTS}).")
    raise AssertionError("unreachable")


def _load_large_part_transaction(database: connection, config: LargeTableLoad, csv_path: Path, checksum: str) -> LoadOutcome:
    """Execute one atomic COPY/staging transaction for a large source part.

    Used for each retry attempt by :func:`load_large_part`. It locks the final
    table, rechecks the checkpoint, synchronizes the serial sequence, clears
    stale staging data, validates and COPY-streams the CSV, performs its UPSERT,
    clears staging again, and writes the checkpoint before committing. It
    returns the committed or lock-time skip outcome and rolls back on any error.
    """
    row_count = 0
    try:
        with database.cursor() as db_cursor:
            # Lock final rows first so concurrent processes cannot both load a part.
            db_cursor.execute(pg_sql.SQL("LOCK TABLE {} IN EXCLUSIVE MODE").format(pg_sql.Identifier(config.table)))
            checkpoint = read_checkpoint_in_transaction(db_cursor, config.table, csv_path.name)
            if checkpoint:
                outcome = _checkpoint_outcome(config.table, csv_path, checksum, checkpoint, after_lock=True)
                database.commit()
                return outcome

            synchronize_sequence(db_cursor, config)
            _truncate_staging(db_cursor, config)
            _validate_copy_header(csv_path, config)
            _copy_to_staging(database, db_cursor, csv_path, config)

            db_cursor.execute(pg_sql.SQL("SELECT count(*) FROM {}").format(pg_sql.Identifier(config.staging_table)))
            row_count = db_cursor.fetchone()[0]
            db_cursor.execute(staging_upsert_statement(config))
            if config.validate_order_ids:
                validate_order_ids(db_cursor.fetchall(), row_count)
            _truncate_staging(db_cursor, config)
            write_checkpoint(db_cursor, config.table, csv_path.name, checksum, row_count)
        database.commit()
        print(f"LOADED {config.table} {csv_path.name}: {row_count:,} rows.")
        return LoadOutcome(row_count)
    except Exception as exc:
        database.rollback()
        raise TableLoadError(f"Rolled back {config.table} part load from {csv_path}: {exc}") from exc


def _checkpoint_outcome(table: str, csv_path: Path, checksum: str, checkpoint, *, after_lock: bool = False) -> LoadOutcome:
    """Reject changed completed input or produce the matching skip result."""
    if checkpoint[0] != checksum:
        raise CheckpointMismatchError(f"CHECKSUM MISMATCH for {table} {csv_path.name}: source file changed")
    location = " after lock" if after_lock else ""
    print(f"SKIPPED {table} {csv_path.name} (checkpoint{location}).")
    return LoadOutcome(checkpoint[1], skipped=True)


def _truncate_staging(db_cursor: cursor, config: LargeTableLoad) -> None:
    """Clear an order-related staging table within the current part transaction.

    Called before COPY to isolate a retry from stale rows and after the final
    UPSERT so a committed part leaves no staging residue for the next file.
    """
    db_cursor.execute(pg_sql.SQL("TRUNCATE TABLE {}").format(pg_sql.Identifier(config.staging_table)))


def _validate_copy_header(csv_path: Path, config: LargeTableLoad) -> None:
    """Fail before COPY when a part's CSV contract does not match staging columns."""
    with csv_path.open("r", encoding="utf-8", newline="") as source:
        header = next(csv.reader(source), None)
    if header != list(config.columns):
        raise ValueError(f"Unexpected columns in {csv_path}; expected {list(config.columns)}, received {header}")


def _copy_to_staging(database: connection, db_cursor: cursor, csv_path: Path, config: LargeTableLoad) -> None:
    """Stream one validated CSV part directly into its simple staging table."""
    statement = pg_sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE, NULL '')").format(
        pg_sql.Identifier(config.staging_table),
        pg_sql.SQL(", ").join(map(pg_sql.Identifier, config.columns)),
    )
    with csv_path.open("r", encoding="utf-8", newline="") as source:
        db_cursor.copy_expert(statement.as_string(database), source)


def staging_upsert_statement(config: LargeTableLoad) -> pg_sql.Composed:
    """Build the ordered staging-to-final UPSERT for an order-related table."""
    update_columns = [column for column in config.final_columns if column not in config.conflict_columns]
    assignments = [
        pg_sql.SQL("{} = EXCLUDED.{}").format(pg_sql.Identifier(column), pg_sql.Identifier(column))
        for column in update_columns
    ]
    assignments.append(pg_sql.SQL("loaded_at = CURRENT_TIMESTAMP"))
    returning = pg_sql.SQL("")
    if config.validate_order_ids:
        returning = pg_sql.SQL(" RETURNING {}, {}").format(pg_sql.Identifier(config.primary_key), pg_sql.Identifier("order_code"))
    return pg_sql.SQL(
        "INSERT INTO {table} ({columns}) SELECT {columns} FROM {staging} ORDER BY staging_row_id "
        "ON CONFLICT ({conflicts}) DO UPDATE SET {assignments}{returning}"
    ).format(
        table=pg_sql.Identifier(config.table),
        columns=pg_sql.SQL(", ").join(map(pg_sql.Identifier, config.final_columns)),
        staging=pg_sql.Identifier(config.staging_table),
        conflicts=pg_sql.SQL(", ").join(map(pg_sql.Identifier, config.conflict_columns)),
        assignments=pg_sql.SQL(", ").join(assignments),
        returning=returning,
    )


def validate_order_ids(generated_rows: list[tuple[int, str]], expected_count: int) -> None:
    """Verify generated order IDs retain the source's expected positional mapping."""
    if len(generated_rows) != expected_count:
        raise ValueError(f"Expected {expected_count} generated order IDs, received {len(generated_rows)}")
    for order_id, order_code in generated_rows:
        if not order_code.startswith("ORD-") or not order_code[4:].isdigit():
            raise ValueError(f"Invalid order_code returned from staging: {order_code}")
        if order_id != int(order_code[4:]):
            raise ValueError(f"order_id {order_id} does not match expected source ID {order_code[4:]}")
