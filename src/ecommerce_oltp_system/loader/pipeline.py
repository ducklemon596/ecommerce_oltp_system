"""Schema-and-load orchestration for the generated PostgreSQL dataset."""

from __future__ import annotations

import argparse
from contextlib import closing
from pathlib import Path
from time import perf_counter

import psycopg2
from psycopg2.extensions import connection

from .config import ORDER_ITEM_LOAD, ORDER_LOAD, TABLE_LOADS
from .exceptions import CheckpointMismatchError, TableLoadError
from .strategies.large_part import load_large_part
from .models import LargeTableLoad, LoadOutcome, TableLoad
from .db.connection import database_config
from .db.schema import apply_schema
from .strategies.small_table import load_table

__all__ = [
    "CheckpointMismatchError", "LargeTableLoad", "LoadOutcome", "ORDER_ITEM_LOAD",
    "ORDER_LOAD", "TABLE_LOADS", "TableLoad", "TableLoadError", "apply_schema",
    "database_config", "load_all", "load_large_part", "load_table",
]


def load_all(database: connection, data_dir: str | Path = "data") -> dict[str, int]:
    """Run the complete PostgreSQL loading pipeline for one generated dataset.

    This orchestration step expects reference CSV files plus paired order and
    order-item part folders below ``data_dir``. It loads master/dependent tables
    from :data:`TABLE_LOADS` first, then loads each order part before its matching
    order-item part so positional generated order IDs satisfy foreign keys.

    Returns a mapping of table name to source row count. Each delegated loader
    owns its documented transaction, retry, checkpoint, sequence-sync, and
    staging-cleanup behavior; this function only enforces dependency order and
    emits concise per-table timing statistics.
    """
    paths, order_paths, order_item_paths = validate_source_paths(Path(data_dir))
    loaded: dict[str, int] = {}
    for config in TABLE_LOADS:
        started_at = perf_counter()
        outcome = load_table(database, config, paths[config.table])
        elapsed_seconds = perf_counter() - started_at
        loaded[config.table] = outcome.row_count
        status = "SKIPPED" if outcome.skipped else "LOADED"
        print(f"{status} {outcome.row_count:,} rows for {config.table} in {elapsed_seconds:.2f}s.")

    order_rows = order_item_rows = 0
    order_elapsed = item_elapsed = 0.0
    for order_path, order_item_path in zip(order_paths, order_item_paths):
        started_at = perf_counter()
        order_outcome = load_large_part(database, ORDER_LOAD, order_path)
        order_rows += order_outcome.row_count
        order_elapsed += perf_counter() - started_at

        started_at = perf_counter()
        item_outcome = load_large_part(database, ORDER_ITEM_LOAD, order_item_path)
        order_item_rows += item_outcome.row_count
        item_elapsed += perf_counter() - started_at

    loaded["order"] = order_rows
    loaded["order_item"] = order_item_rows
    print(f"Processed {order_rows:,} source rows for order from {len(order_paths)} parts in {order_elapsed:.2f}s (completed parts skipped).")
    print(f"Processed {order_item_rows:,} source rows for order_item from {len(order_item_paths)} parts in {item_elapsed:.2f}s (completed parts skipped).")
    return loaded


def validate_source_paths(source_dir: Path) -> tuple[dict[str, Path], list[Path], list[Path]]:
    """Check required files and paired parts before schema or file commits."""
    paths = {config.table: source_dir / f"{config.table}.csv" for config in TABLE_LOADS}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing CSV file(s): {', '.join(missing)}")

    order_paths, order_item_paths = find_paired_order_part_paths(source_dir)
    return paths, order_paths, order_item_paths


def find_paired_order_part_paths(source_dir: Path) -> tuple[list[Path], list[Path]]:
    """Locate and pair generated order files for the large-table load stage.

    ``source_dir`` must contain matching numeric part suffixes in ``orders``
    and ``order_items``. The returned path lists share that numeric order so
    :func:`load_all` can commit an order parent part before its item child part.
    No database or file-write side effects occur here.
    """
    order_parts = {parse_part_number(path, "order_part_"): path for path in (source_dir / "orders").glob("order_part_*.csv")}
    order_item_parts = {parse_part_number(path, "order_item_part_"): path for path in (source_dir / "order_items").glob("order_item_part_*.csv")}
    if not order_parts or not order_item_parts:
        raise FileNotFoundError("Missing order or order_item part files")
    invalid = [str(path) for path in (*order_parts.values(), *order_item_parts.values()) if not path.is_file()]
    if invalid:
        raise FileNotFoundError(f"Expected CSV part files, found non-files: {', '.join(invalid)}")
    if order_parts.keys() != order_item_parts.keys():
        raise ValueError("Order and order_item part numbers do not match")
    numbers = sorted(order_parts)
    return [order_parts[number] for number in numbers], [order_item_parts[number] for number in numbers]


def parse_part_number(path: Path, prefix: str) -> int:
    """Extract one validated part number used to pair order-related CSV files.

    This is used only while arranging large-table load order. It accepts a
    generated filename and expected prefix, returning its integer suffix or
    raising ``ValueError`` before any database transaction starts.
    """
    if not path.stem.startswith(prefix):
        raise ValueError(f"Unexpected part filename: {path.name}")
    try:
        return int(path.stem.removeprefix(prefix))
    except ValueError as exc:
        raise ValueError(f"Unexpected part filename: {path.name}") from exc


def configure_parser(parser: argparse.ArgumentParser, *, initialization_only: bool = False) -> None:
    """Share connection/load options across the ``init-db`` and ``load`` CLI commands."""
    parser.add_argument("--config", type=Path, default=Path("database.ini"), help="PostgreSQL INI file (defaults to database.ini).")
    parser.add_argument("--section", default="postgresql")
    if initialization_only:
        parser.set_defaults(schema_only=True, skip_schema=False, data_dir=Path("data"))
        return
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--schema-only", action="store_true", help="Create tables without loading CSVs.")
    parser.add_argument("--skip-schema", action="store_true", help="Load CSVs without applying schema.sql.")
    parser.add_argument("--indexes", choices=("recommended", "none"), default=None,
                        help="After a successful load, deploy reporting functions and optionally C1+C2. Omitted: load only.")
    parser.add_argument("--sql-dir", type=Path, default=Path("database"), help="SQL assets for --indexes, from the repository checkout.")


def run(args: argparse.Namespace) -> None:
    """Run the public schema-and-load command-line workflow.

    The entry point reads ``database.ini``, optionally applies the packaged
    schema, and then invokes :func:`load_all` for the supplied data directory.
    Schema application and each file load retain their own transactional side
    effects; this function creates the connection and reports total elapsed time.
    """
    if args.schema_only and args.skip_schema:
        raise SystemExit("--schema-only and --skip-schema cannot be used together.")
    if args.schema_only and getattr(args, "indexes", None) is not None:
        raise SystemExit("Use ecommerce setup for reporting/index installation without a data load.")
    from ..database_setup import prepare_database, read_setup_sql

    stage = "validate inputs"
    try:
        settings = database_config(args.config, args.section)
        if not args.schema_only:
            validate_source_paths(args.data_dir)
        prepared = read_setup_sql(args.sql_dir, args.indexes) if getattr(args, "indexes", None) is not None else None
        stage = "connect to PostgreSQL"
        with closing(psycopg2.connect(**settings)) as database:
            if not args.skip_schema:
                stage = "apply schema"
                apply_schema(database)
                print("PostgreSQL schema is ready.")
            if not args.schema_only:
                stage = "load CSV files"
                started_at = perf_counter()
                loaded = load_all(database, args.data_dir)
                print(f"Ingestion complete: processed {sum(loaded.values()):,} source rows in {perf_counter() - started_at:.2f}s (completed files skipped).")
                if prepared is not None:
                    stage = "install reporting functions/indexes after ingestion"
                    prepare_database(database, args.sql_dir, args.indexes, schema=False, prepared=prepared)
    except (psycopg2.Error, OSError, ValueError, TableLoadError, CheckpointMismatchError) as error:
        recovery = ""
        if stage == "load CSV files":
            recovery = " Earlier successful files remain committed. Fix the error and rerun with the same unchanged dataset; checkpoints skip completed files."
        elif stage == "install reporting functions/indexes after ingestion":
            recovery = " Data ingestion is already committed; setup failed in its separate transaction. Fix the error and run ecommerce setup with the same --config, --section, --sql-dir and --indexes values."
        raise SystemExit(f"Cannot {stage}: {error}.{recovery}") from error
