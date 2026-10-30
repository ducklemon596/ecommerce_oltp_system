"""Explicit installation of existing SQL assets and recommended optional indexes."""

import argparse
import re
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

import psycopg2
from psycopg2.extensions import connection

from .loader.db.connection import database_config
from .loader.db.schema import apply_schema


RECOMMENDED_INDEXES = (
    "order_order_id_deleted_idx",
    "order_item_product_order_cover_idx",
)


def recommended_index_sql(sql_dir: Path) -> list[str]:
    """Select C1/C2 verbatim from historical DDL; never install the whole file."""
    source = (sql_dir / "indexes.sql").read_text(encoding="utf-8")
    by_name = {name: statement for statement, name in re.findall(
        r"(CREATE INDEX IF NOT EXISTS (\w+)\s+.*?;)", source, re.S
    )}
    missing = set(RECOMMENDED_INDEXES) - by_name.keys()
    if missing:
        raise ValueError(f"Recommended index definitions missing: {', '.join(sorted(missing))}")
    return [by_name[name] for name in RECOMMENDED_INDEXES]


@dataclass(frozen=True)
class SetupSQL:
    """Validated checkout assets, read before opening a mutating connection."""

    functions: str
    indexes: tuple[str, ...]


def read_setup_sql(sql_dir: Path, indexes: str) -> SetupSQL:
    """Fail early when requested checkout SQL is missing or incomplete."""
    try:
        functions = (sql_dir / "reporting/functions.sql").read_text(encoding="utf-8")
        statements = recommended_index_sql(sql_dir) if indexes == "recommended" else []
    except OSError as error:
        raise OSError(f"Cannot read required setup SQL under {sql_dir}: {error}. Run from the repository root or use --sql-dir with a complete checkout.") from error
    if not functions.strip():
        raise ValueError("Reporting functions SQL is empty. Use --sql-dir with a complete repository checkout.")
    return SetupSQL(functions, tuple(statements))


def prepare_database(database: connection, sql_dir: Path, indexes: str, *, schema: bool = True,
                     prepared: SetupSQL | None = None) -> None:
    """Install unchanged functions and optionally C1/C2 in an explicit transaction.

    ``none`` skips optional index creation; it never removes existing indexes.
    Existing same-name indexes are left untouched by IF NOT EXISTS.
    """
    prepared = prepared or read_setup_sql(sql_dir, indexes)
    if schema:
        apply_schema(database)
    with database:
        with database.cursor() as cursor:
            cursor.execute(prepared.functions)
            if prepared.indexes:
                cursor.execute("SET LOCAL max_parallel_maintenance_workers = 0")
                for statement in prepared.indexes:
                    cursor.execute(statement)
    print("Reporting functions are ready.")
    print("Optional indexes: C1+C2 requested (existing indexes preserved)." if prepared.indexes
          else "Optional index creation skipped; existing indexes preserved.")


def configure_parser(parser: argparse.ArgumentParser) -> None:
    """Expose setup independently for already loaded databases."""
    parser.add_argument("--config", type=Path, default=Path("database.ini"))
    parser.add_argument("--section", default="postgresql")
    parser.add_argument("--sql-dir", type=Path, default=Path("database"), help="SQL assets in the repository checkout.")
    parser.add_argument("--indexes", choices=("recommended", "none"), default="recommended",
                        help="Create C1+C2 after schema/functions (default), or skip optional indexes.")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> None:
    """Prepare the configured database; database creation belongs to Compose."""
    try:
        settings = database_config(args.config, args.section)
        prepared = read_setup_sql(args.sql_dir, args.indexes)
        with closing(psycopg2.connect(**settings)) as database:
            prepare_database(database, args.sql_dir, args.indexes, prepared=prepared)
    except (psycopg2.Error, OSError, ValueError) as error:
        raise SystemExit(f"Cannot prepare database: {error}") from error
