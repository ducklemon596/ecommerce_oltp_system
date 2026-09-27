"""File checksums and transactional checkpoint persistence for loader restarts."""

from __future__ import annotations

import hashlib
from pathlib import Path

from psycopg2.extensions import connection, cursor


def file_checksum(csv_path: Path) -> str:
    """Calculate the source-file identity for the loader checkpoint stage.

    Called before every small-table file and large order-related part is loaded.
    ``csv_path`` is streamed in fixed chunks and its SHA-256 digest is returned;
    no database state is read or changed. The digest lets restart logic skip only
    a completed file whose contents have not changed.
    """
    digest = hashlib.sha256()
    with csv_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_checkpoint(database: connection, table_name: str, file_name: str):
    """Read a prior file checkpoint before starting a load transaction.

    Both loader strategies call this restart-check step using their database
    connection, table name, and source filename. It returns ``(checksum,
    row_count)`` or ``None`` and rolls back the read-only implicit transaction so
    the subsequent load can begin cleanly. It never creates or updates a checkpoint.
    """
    with database.cursor() as db_cursor:
        result = read_checkpoint_in_transaction(db_cursor, table_name, file_name)
    database.rollback()
    return result


def read_checkpoint_in_transaction(db_cursor: cursor, table_name: str, file_name: str):
    """Read a checkpoint inside the active locked file-load transaction.

    This second check closes the concurrent-loader race after a final table lock
    is acquired. It returns the stored checksum/count or ``None`` and deliberately
    leaves commit or rollback ownership with the calling loading strategy.
    """
    db_cursor.execute(
        "SELECT file_checksum, row_count FROM load_checkpoint WHERE table_name = %s AND file_name = %s",
        (table_name, file_name),
    )
    return db_cursor.fetchone()


def write_checkpoint(db_cursor: cursor, table_name: str, file_name: str, checksum: str, row_count: int) -> None:
    """Record a completed CSV file in the caller's active load transaction.

    Small-table UPSERT and large COPY/staging strategies call this only after all
    source rows have been applied. ``checksum`` and ``row_count`` become the
    restart identity for ``table_name``/``file_name``. The caller commits or rolls
    back both data rows and this insert together, so no partial completion is saved.
    """
    db_cursor.execute(
        "INSERT INTO load_checkpoint (table_name, file_name, file_checksum, row_count) VALUES (%s, %s, %s, %s)",
        (table_name, file_name, checksum, row_count),
    )
