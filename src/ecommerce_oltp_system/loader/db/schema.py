"""Packaged PostgreSQL schema application."""

from importlib.resources import files

from psycopg2.extensions import connection


def apply_schema(database: connection) -> None:
    """Apply the packaged PostgreSQL DDL before the data-loading pipeline.

    Called by the public loader CLI unless ``--skip-schema`` is selected.
    ``database`` is an open psycopg2 connection; the package's ``schema.sql``
    creates final, staging, and checkpoint tables plus their constraints. The
    function returns ``None`` and commits the complete schema script on success
    or rolls it back on any DDL error, before file loading starts.
    """
    schema_sql = files("ecommerce_oltp_system.loader.sql").joinpath("schema.sql").read_text(encoding="utf-8")
    try:
        with database.cursor() as db_cursor:
            db_cursor.execute(schema_sql)
        database.commit()
    except Exception:
        database.rollback()
        raise
