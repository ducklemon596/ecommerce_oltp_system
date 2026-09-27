"""Transactional PostgreSQL loader for generated CSV files."""

from __future__ import annotations

import argparse
import csv
import configparser
import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from importlib.resources import files
from time import perf_counter
from pathlib import Path
from typing import Callable

import psycopg2
from psycopg2.extras import execute_values
from psycopg2 import sql as pg_sql
from psycopg2.extensions import connection, cursor


AUDIT_COLUMNS = (
    "created_at",
    "created_by",
    "updated_at",
    "updated_by",
    "deleted_at",
    "deleted_by",
    "is_deleted",
)

UPSERT_BATCH_SIZE = 1_000
PART_LOAD_ATTEMPTS = 2



@dataclass(frozen=True)
class TableLoad:
    """Static loading metadata for one CSV-backed table."""

    table: str
    primary_key: str
    columns: tuple[str, ...]
    conflict_columns: tuple[str, ...]
    requires_positional_ids: bool = False

    @property
    def csv_columns(self) -> tuple[str, ...]:
        return (*self.columns, "loaded_at")




@dataclass(frozen=True)
class LargeTableLoad:
    """COPY/staging metadata for one high-volume part-file table."""

    table: str
    staging_table: str
    primary_key: str
    columns: tuple[str, ...]
    conflict_columns: tuple[str, ...]
    validate_order_ids: bool = False

    @property
    def final_columns(self) -> tuple[str, ...]:
        return tuple(column for column in self.columns if column != "loaded_at")


ORDER_LOAD = LargeTableLoad(
    table="order",
    staging_table="staging_order",
    primary_key="order_id",
    columns=(
        "customer_id",
        "order_code",
        "order_date",
        "status",
        "total_amount",
        *AUDIT_COLUMNS,
        "loaded_at",
    ),
    conflict_columns=("order_code",),
    validate_order_ids=True,
)

ORDER_ITEM_LOAD = LargeTableLoad(
    table="order_item",
    staging_table="staging_order_item",
    primary_key="order_item_id",
    columns=(
        "order_id",
        "order_item_code",
        "product_id",
        "order_date",
        "quantity",
        "unit_price",
        "subtotal",
        *AUDIT_COLUMNS,
        "loaded_at",
    ),
    conflict_columns=("order_item_code",),
)
TABLE_LOADS = (
    TableLoad(
        "brand",
        "brand_id",
        ("brand_code", "brand_name", "country", *AUDIT_COLUMNS),
        ("brand_code",),
        True,
    ),
    TableLoad(
        "category",
        "category_id",
        (
            "category_code",
            "category_name",
            "parent_category_id",
            "level",
            *AUDIT_COLUMNS,
        ),
        ("category_code",),
        True,
    ),
    TableLoad(
        "seller",
        "seller_id",
        (
            "seller_code",
            "seller_name",
            "join_date",
            "created_at",
            "seller_type",
            "rating",
            "country",
            "created_by",
            "updated_at",
            "updated_by",
            "deleted_at",
            "deleted_by",
            "is_deleted",
        ),
        ("seller_code",),
        True,
    ),
    TableLoad(
        "customer",
        "customer_id",
        (
            "customer_code",
            "customer_name",
            "email",
            "phone",
            "gender",
            "address",
            "city",
            *AUDIT_COLUMNS,
        ),
        ("customer_code",),
        True,
    ),
    TableLoad(
        "product",
        "product_id",
        (
            "product_code",
            "product_name",
            "category_id",
            "brand_id",
            "seller_id",
            "price",
            "stock_qty",
            "rating",
            "created_at",
            "is_active",
            "created_by",
            "updated_at",
            "updated_by",
            "deleted_at",
            "deleted_by",
            "is_deleted",
        ),
        ("product_code",),
        True,
    ),
    TableLoad(
        "promotion",
        "promotion_id",
        (
            "promotion_code",
            "promotion_name",
            "promotion_type",
            "discount_type",
            "discount_value",
            "start_date",
            "end_date",
            *AUDIT_COLUMNS,
        ),
        ("promotion_code",),
        True,
    ),
    TableLoad(
        "promotion_product",
        "promo_product_id",
        ("promotion_id", "promotion_product_code", "product_id", *AUDIT_COLUMNS),
        ("promotion_product_code",),
    ),
)


INTEGER_COLUMNS = {
    "parent_category_id",
    "level",
    "category_id",
    "brand_id",
    "seller_id",
    "stock_qty",
    "promotion_id",
    "product_id",
}
DECIMAL_COLUMNS = {"rating", "price", "discount_value"}
DATE_COLUMNS = {"join_date", "start_date", "end_date"}
TIMESTAMP_COLUMNS = {"created_at", "updated_at", "deleted_at"}
BOOLEAN_COLUMNS = {"is_active", "is_deleted"}


class TableLoadError(RuntimeError):
    """Raised after one complete table transaction has been rolled back."""


class CheckpointMismatchError(RuntimeError):
    """Raised when a completed source file has changed on disk."""


@dataclass(frozen=True)
class LoadOutcome:
    """Committed or checkpoint-skipped row count for one source file."""

    row_count: int
    skipped: bool = False


def apply_schema(database: connection) -> None:
    """Apply the packaged schema in one transaction."""

    schema_sql = (
        files("ecommerce_oltp_system.loader.sql")
        .joinpath("schema.sql")
        .read_text(encoding="utf-8")
    )
    try:
        with database.cursor() as db_cursor:
            db_cursor.execute(schema_sql)
        database.commit()
    except Exception:
        database.rollback()
        raise


def load_all(database: connection, data_dir: str | Path = "data") -> dict[str, int]:
    """Load reference files, then each matching order and item part pair."""

    source_dir = Path(data_dir)
    paths = {
        config.table: source_dir / f"{config.table}.csv" for config in TABLE_LOADS
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing CSV file(s): {', '.join(missing)}")

    loaded: dict[str, int] = {}
    for config in TABLE_LOADS:
        started_at = perf_counter()
        outcome = load_table(database, config, paths[config.table])
        elapsed_seconds = perf_counter() - started_at
        loaded[config.table] = outcome.row_count
        status = "SKIPPED" if outcome.skipped else "LOADED"
        print(
            f"{status} {outcome.row_count:,} rows for {config.table} "
            f"in {elapsed_seconds:.2f}s."
        )

    order_paths, order_item_paths = _paired_part_paths(source_dir)
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
    print(
        f"Loaded {order_rows:,} rows into order from {len(order_paths)} parts "
        f"in {order_elapsed:.2f}s."
    )
    print(
        f"Loaded {order_item_rows:,} rows into order_item from "
        f"{len(order_item_paths)} parts in {item_elapsed:.2f}s."
    )
    return loaded


def _paired_part_paths(source_dir: Path) -> tuple[list[Path], list[Path]]:
    order_parts = {
        _part_number(path, "order_part_"): path
        for path in (source_dir / "orders").glob("order_part_*.csv")
    }
    order_item_parts = {
        _part_number(path, "order_item_part_"): path
        for path in (source_dir / "order_items").glob("order_item_part_*.csv")
    }
    if not order_parts or not order_item_parts:
        raise FileNotFoundError("Missing order or order_item part files")
    if order_parts.keys() != order_item_parts.keys():
        raise ValueError("Order and order_item part numbers do not match")

    part_numbers = sorted(order_parts)
    return (
        [order_parts[number] for number in part_numbers],
        [order_item_parts[number] for number in part_numbers],
    )


def _part_number(path: Path, prefix: str) -> int:
    stem = path.stem
    if not stem.startswith(prefix):
        raise ValueError(f"Unexpected part filename: {path.name}")
    try:
        return int(stem.removeprefix(prefix))
    except ValueError as exc:
        raise ValueError(f"Unexpected part filename: {path.name}") from exc


def load_large_part(
    database: connection, config: LargeTableLoad, csv_path: Path
) -> LoadOutcome:
    """Load one part, retrying it once after a rolled-back failure."""

    checksum = _file_checksum(csv_path)
    checkpoint = _checkpoint(database, config.table, csv_path.name)
    if checkpoint:
        if checkpoint[0] != checksum:
            raise CheckpointMismatchError(
                f"CHECKSUM MISMATCH for {config.table} {csv_path.name}: source file changed"
            )
        print(f"SKIPPED {config.table} {csv_path.name} (checkpoint).")
        return LoadOutcome(checkpoint[1], skipped=True)
    for attempt in range(1, PART_LOAD_ATTEMPTS + 1):
        try:
            return _load_large_part_once(database, config, csv_path, checksum)
        except TableLoadError:
            if attempt == PART_LOAD_ATTEMPTS:
                raise
            print(f"RETRY {config.table} {csv_path.name} (attempt {attempt + 1}/{PART_LOAD_ATTEMPTS}).")
    raise AssertionError("unreachable")


def _load_large_part_once(
    database: connection, config: LargeTableLoad, csv_path: Path, checksum: str
) -> LoadOutcome:
    """COPY one part to staging, UPSERT it to final, then clear staging."""

    row_count = 0
    try:
        with database.cursor() as db_cursor:
            db_cursor.execute(
                pg_sql.SQL("LOCK TABLE {} IN EXCLUSIVE MODE").format(
                    pg_sql.Identifier(config.table)
                )
            )
            locked_checkpoint = _checkpoint_in_transaction(
                db_cursor, config.table, csv_path.name
            )
            if locked_checkpoint:
                if locked_checkpoint[0] != checksum:
                    raise CheckpointMismatchError(
                        f"CHECKSUM MISMATCH for {config.table} {csv_path.name}: source file changed"
                    )
                database.commit()
                print(f"SKIPPED {config.table} {csv_path.name} (checkpoint after lock).")
                return LoadOutcome(locked_checkpoint[1], skipped=True)
            _synchronize_sequence(db_cursor, config)
            db_cursor.execute(
                pg_sql.SQL("TRUNCATE TABLE {}").format(
                    pg_sql.Identifier(config.staging_table)
                )
            )

            with csv_path.open("r", encoding="utf-8", newline="") as source:
                header = next(csv.reader(source), None)
            if header != list(config.columns):
                raise ValueError(
                    f"Unexpected columns in {csv_path}; expected "
                    f"{list(config.columns)}, received {header}"
                )

            copy_statement = pg_sql.SQL(
                "COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE, NULL '')"
            ).format(
                pg_sql.Identifier(config.staging_table),
                pg_sql.SQL(", ").join(map(pg_sql.Identifier, config.columns)),
            )
            with csv_path.open("r", encoding="utf-8", newline="") as source:
                db_cursor.copy_expert(copy_statement.as_string(database), source)

            db_cursor.execute(
                pg_sql.SQL("SELECT count(*) FROM {}").format(
                    pg_sql.Identifier(config.staging_table)
                )
            )
            row_count = db_cursor.fetchone()[0]
            db_cursor.execute(_staging_upsert_statement(config))
            if config.validate_order_ids:
                _validate_order_ids(db_cursor.fetchall(), row_count)
            db_cursor.execute(
                pg_sql.SQL("TRUNCATE TABLE {}").format(
                    pg_sql.Identifier(config.staging_table)
                )
            )
            _write_checkpoint(db_cursor, config.table, csv_path.name, checksum, row_count)
        database.commit()
        print(f"LOADED {config.table} {csv_path.name}: {row_count:,} rows.")
        return LoadOutcome(row_count)
    except Exception as exc:
        database.rollback()
        raise TableLoadError(
            f"Rolled back {config.table} part load from {csv_path}: {exc}"
        ) from exc


def _staging_upsert_statement(config: LargeTableLoad) -> pg_sql.Composed:
    update_columns = [
        column
        for column in config.final_columns
        if column not in config.conflict_columns
    ]
    assignments = [
        pg_sql.SQL("{} = EXCLUDED.{}").format(
            pg_sql.Identifier(column), pg_sql.Identifier(column)
        )
        for column in update_columns
    ]
    assignments.append(pg_sql.SQL("loaded_at = CURRENT_TIMESTAMP"))
    returning = pg_sql.SQL("")
    if config.validate_order_ids:
        returning = pg_sql.SQL(" RETURNING {}, {}").format(
            pg_sql.Identifier(config.primary_key),
            pg_sql.Identifier("order_code"),
        )

    return pg_sql.SQL(
        "INSERT INTO {table} ({columns}) "
        "SELECT {columns} FROM {staging} ORDER BY staging_row_id "
        "ON CONFLICT ({conflicts}) DO UPDATE SET {assignments}{returning}"
    ).format(
        table=pg_sql.Identifier(config.table),
        columns=pg_sql.SQL(", ").join(
            map(pg_sql.Identifier, config.final_columns)
        ),
        staging=pg_sql.Identifier(config.staging_table),
        conflicts=pg_sql.SQL(", ").join(
            map(pg_sql.Identifier, config.conflict_columns)
        ),
        assignments=pg_sql.SQL(", ").join(assignments),
        returning=returning,
    )


def _validate_order_ids(
    generated_rows: list[tuple[int, str]], expected_count: int
) -> None:
    if len(generated_rows) != expected_count:
        raise ValueError(
            f"Expected {expected_count} generated order IDs, received "
            f"{len(generated_rows)}"
        )
    for order_id, order_code in generated_rows:
        if not order_code.startswith("ORD-") or not order_code[4:].isdigit():
            raise ValueError(f"Invalid order_code returned from staging: {order_code}")
        if order_id != int(order_code[4:]):
            raise ValueError(
                f"order_id {order_id} does not match expected source ID "
                f"{order_code[4:]}"
            )


def load_table(database: connection, config: TableLoad, csv_path: Path) -> LoadOutcome:
    """Load one CSV in one transaction, rolling back the table on any failure."""

    checksum = _file_checksum(csv_path)
    checkpoint = _checkpoint(database, config.table, csv_path.name)
    if checkpoint:
        if checkpoint[0] != checksum:
            raise CheckpointMismatchError(
                f"CHECKSUM MISMATCH for {config.table} {csv_path.name}: source file changed"
            )
        print(f"SKIPPED {config.table} {csv_path.name} (checkpoint).")
        return LoadOutcome(checkpoint[1], skipped=True)
    row_number = 0
    try:
        with database.cursor() as db_cursor:
            db_cursor.execute(
                pg_sql.SQL("LOCK TABLE {} IN EXCLUSIVE MODE").format(
                    pg_sql.Identifier(config.table)
                )
            )
            locked_checkpoint = _checkpoint_in_transaction(
                db_cursor, config.table, csv_path.name
            )
            if locked_checkpoint:
                if locked_checkpoint[0] != checksum:
                    raise CheckpointMismatchError(
                        f"CHECKSUM MISMATCH for {config.table} {csv_path.name}: source file changed"
                    )
                database.commit()
                print(f"SKIPPED {config.table} {csv_path.name} (checkpoint after lock).")
                return LoadOutcome(locked_checkpoint[1], skipped=True)
            _synchronize_sequence(db_cursor, config)
            statement = _upsert_statement(config)

            with csv_path.open("r", encoding="utf-8", newline="") as source:
                reader = csv.DictReader(source)
                _validate_header(reader.fieldnames, config, csv_path)
                batch: list[tuple[int, tuple[object, ...]]] = []
                for row_number, row in enumerate(reader, start=1):
                    if row["loaded_at"]:
                        raise ValueError(
                            "loaded_at must be empty so PostgreSQL can set it"
                        )
                    values = tuple(
                        _parse_value(column, row[column]) for column in config.columns
                    )
                    batch.append((row_number, values))
                    if len(batch) == UPSERT_BATCH_SIZE:
                        _upsert_batch(db_cursor, statement, config, batch)
                        batch.clear()
                if batch:
                    _upsert_batch(db_cursor, statement, config, batch)
            _write_checkpoint(db_cursor, config.table, csv_path.name, checksum, row_number)
        database.commit()
        print(f"LOADED {config.table} {csv_path.name}: {row_number:,} rows.")
        return LoadOutcome(row_number)
    except Exception as exc:
        database.rollback()
        location = f" at data row {row_number}" if row_number else ""
        raise TableLoadError(
            f"Rolled back {config.table} load from {csv_path}{location}: {exc}"
        ) from exc


def _file_checksum(csv_path: Path) -> str:
    digest = hashlib.sha256()
    with csv_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checkpoint(database: connection, table_name: str, file_name: str):
    with database.cursor() as db_cursor:
        result = _checkpoint_in_transaction(db_cursor, table_name, file_name)
    database.rollback()
    return result


def _checkpoint_in_transaction(db_cursor: cursor, table_name: str, file_name: str):
    db_cursor.execute(
        "SELECT file_checksum, row_count FROM load_checkpoint WHERE table_name = %s AND file_name = %s",
        (table_name, file_name),
    )
    return db_cursor.fetchone()


def _write_checkpoint(db_cursor: cursor, table_name: str, file_name: str, checksum: str, row_count: int) -> None:
    db_cursor.execute(
        "INSERT INTO load_checkpoint (table_name, file_name, file_checksum, row_count) VALUES (%s, %s, %s, %s)",
        (table_name, file_name, checksum, row_count),
    )

def _upsert_batch(
    db_cursor: cursor,
    statement: pg_sql.Composed,
    config: TableLoad,
    batch: list[tuple[int, tuple[object, ...]]],
) -> None:
    """UPSERT one bounded CSV batch and verify positional generated IDs."""

    generated_rows = execute_values(
        db_cursor,
        statement,
        [values for _, values in batch],
        page_size=len(batch),
        fetch=True,
    )
    if len(generated_rows) != len(batch):
        raise ValueError(
            f"Expected {len(batch)} generated IDs, received {len(generated_rows)}"
        )
    if config.requires_positional_ids:
        for (row_number, _), (generated_id,) in zip(batch, generated_rows):
            if generated_id != row_number:
                raise ValueError(
                    f"{config.primary_key} {generated_id} does not match "
                    f"expected CSV position {row_number}"
                )



def _synchronize_sequence(
    db_cursor: cursor, config: TableLoad | LargeTableLoad
) -> None:
    statement = pg_sql.SQL(
        """
        SELECT setval(
            pg_get_serial_sequence(%s, %s),
            COALESCE(MAX({primary_key}), 1),
            MAX({primary_key}) IS NOT NULL
        )
        FROM {table}
        """
    ).format(
        primary_key=pg_sql.Identifier(config.primary_key),
        table=pg_sql.Identifier(config.table),
    )
    db_cursor.execute(statement, (config.table, config.primary_key))


def _upsert_statement(config: TableLoad) -> pg_sql.Composed:
    update_columns = [
        column for column in config.columns if column not in config.conflict_columns
    ]
    assignments = [
        pg_sql.SQL("{} = EXCLUDED.{}").format(
            pg_sql.Identifier(column), pg_sql.Identifier(column)
        )
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
        conflict_columns=pg_sql.SQL(", ").join(
            map(pg_sql.Identifier, config.conflict_columns)
        ),
        assignments=pg_sql.SQL(", ").join(assignments),
        primary_key=pg_sql.Identifier(config.primary_key),
    )


def _validate_header(
    actual: list[str] | None, config: TableLoad, csv_path: Path
) -> None:
    expected = list(config.csv_columns)
    if actual != expected:
        raise ValueError(
            f"Unexpected columns in {csv_path}; expected {expected}, received {actual}"
        )


def _parse_value(column: str, value: str) -> object:
    if value == "":
        return None
    converter: Callable[[str], object] | None = None
    if column in INTEGER_COLUMNS:
        converter = int
    elif column in DECIMAL_COLUMNS:
        converter = Decimal
    elif column in DATE_COLUMNS:
        converter = date.fromisoformat
    elif column in TIMESTAMP_COLUMNS:
        converter = datetime.fromisoformat
    elif column in BOOLEAN_COLUMNS:
        converter = _parse_boolean
    return converter(value) if converter else value


def _parse_boolean(value: str) -> bool:
    normalized = value.lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def database_config(
    config_path: str | Path, section: str = "postgresql"
) -> dict[str, str]:
    """Read PostgreSQL connection settings from an INI file."""

    parser = configparser.ConfigParser(interpolation=None)
    if not parser.read(config_path):
        raise FileNotFoundError(f"Database configuration file not found: {config_path}")
    if not parser.has_section(section):
        raise ValueError(
            f"Database configuration section [{section}] is missing from {config_path}"
        )

    settings = dict(parser.items(section))
    required = {"host", "database", "user", "password"}
    missing = sorted(required - settings.keys())
    if missing:
        raise ValueError(
            f"Database configuration section [{section}] is missing: {', '.join(missing)}"
        )
    return settings


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create the PostgreSQL schema and load generated CSV files."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("database.ini"),
        help="PostgreSQL INI file (defaults to database.ini).",
    )
    parser.add_argument("--section", default="postgresql")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Create tables without loading CSVs.",
    )
    parser.add_argument(
        "--skip-schema",
        action="store_true",
        help="Load CSVs without applying schema.sql.",
    )
    return parser.parse_args()


def main() -> None:
    """Command-line entry point for schema creation and CSV loading."""

    args = _arguments()
    if args.schema_only and args.skip_schema:
        raise SystemExit("--schema-only and --skip-schema cannot be used together.")

    with psycopg2.connect(**database_config(args.config, args.section)) as database:
        if not args.skip_schema:
            apply_schema(database)
            print("PostgreSQL schema is ready.")
        if not args.schema_only:
            started_at = perf_counter()
            loaded = load_all(database, args.data_dir)
            print(
                f"Complete: loaded {sum(loaded.values()):,} rows in "
                f"{perf_counter() - started_at:.2f}s."
            )


if __name__ == "__main__":
    main()
