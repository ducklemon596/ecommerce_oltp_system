"""Primary-key sequence synchronization used before retried file loads."""

from psycopg2 import sql as pg_sql
from psycopg2.extensions import cursor

from ..models import LargeTableLoad, TableLoad


def synchronize_sequence(db_cursor: cursor, config: TableLoad | LargeTableLoad) -> None:
    """Synchronize a final table's SERIAL sequence inside a file-load transaction.

    Both the small-table UPSERT and large COPY/staging strategies call this just
    after locking their configured final table and before inserting any rows.
    ``config`` supplies the table and primary-key names; the function returns
    ``None`` after executing PostgreSQL ``setval`` through ``db_cursor``.

    PostgreSQL sequence increments survive a rollback. Aligning it with the
    current real maximum key makes a failed/retried file reuse predictable IDs,
    which is required by the generated positional foreign-key convention.
    """
    statement = pg_sql.SQL(
        """
        SELECT setval(
            pg_get_serial_sequence(%s, %s),
            COALESCE(MAX({primary_key}), 1),
            MAX({primary_key}) IS NOT NULL
        )
        FROM {table}
        """
    ).format(primary_key=pg_sql.Identifier(config.primary_key), table=pg_sql.Identifier(config.table))
    db_cursor.execute(statement, (config.table, config.primary_key))
