"""Transactional PostgreSQL loader for generated CSV files."""

from __future__ import annotations

import argparse
import csv
import configparser
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from importlib.resources import files
from pathlib import Path
from typing import Callable

import psycopg2
from psycopg2 import sql
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
            "customer_name",
            "email",
            "phone",
            "gender",
            "address",
            "city",
            *AUDIT_COLUMNS,
        ),
        ("email",),
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
        ("promotion_id", "product_id", *AUDIT_COLUMNS),
        ("promotion_id", "product_id"),
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
    """Load all CSV files in foreign-key dependency order."""

    source_dir = Path(data_dir)
    paths = {
        config.table: source_dir / f"{config.table}.csv" for config in TABLE_LOADS
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing CSV file(s): {', '.join(missing)}")

    return {
        config.table: load_table(database, config, paths[config.table])
        for config in TABLE_LOADS
    }


def load_table(database: connection, config: TableLoad, csv_path: Path) -> int:
    """Load one CSV in one transaction, rolling back the table on any failure."""

    row_number = 0
    try:
        with database.cursor() as db_cursor:
            db_cursor.execute(
                sql.SQL("LOCK TABLE {} IN EXCLUSIVE MODE").format(
                    sql.Identifier(config.table)
                )
            )
            _synchronize_sequence(db_cursor, config)
            statement = _upsert_statement(config)

            with csv_path.open("r", encoding="utf-8", newline="") as source:
                reader = csv.DictReader(source)
                _validate_header(reader.fieldnames, config, csv_path)
                for row_number, row in enumerate(reader, start=1):
                    if row["loaded_at"]:
                        raise ValueError(
                            "loaded_at must be empty so PostgreSQL can set it"
                        )
                    values = [
                        _parse_value(column, row[column]) for column in config.columns
                    ]
                    db_cursor.execute(statement, values)
                    generated_id = db_cursor.fetchone()[0]
                    if config.requires_positional_ids and generated_id != row_number:
                        raise ValueError(
                            f"{config.primary_key} {generated_id} does not match "
                            f"expected CSV position {row_number}"
                        )
        database.commit()
        return row_number
    except Exception as exc:
        database.rollback()
        location = f" at data row {row_number}" if row_number else ""
        raise TableLoadError(
            f"Rolled back {config.table} load from {csv_path}{location}: {exc}"
        ) from exc


def _synchronize_sequence(db_cursor: cursor, config: TableLoad) -> None:
    statement = sql.SQL(
        """
        SELECT setval(
            pg_get_serial_sequence(%s, %s),
            COALESCE(MAX({primary_key}), 1),
            MAX({primary_key}) IS NOT NULL
        )
        FROM {table}
        """
    ).format(
        primary_key=sql.Identifier(config.primary_key),
        table=sql.Identifier(config.table),
    )
    db_cursor.execute(statement, (config.table, config.primary_key))


def _upsert_statement(config: TableLoad) -> sql.Composed:
    update_columns = [
        column for column in config.columns if column not in config.conflict_columns
    ]
    assignments = [
        sql.SQL("{} = EXCLUDED.{}").format(
            sql.Identifier(column), sql.Identifier(column)
        )
        for column in update_columns
    ]
    assignments.append(sql.SQL("loaded_at = CURRENT_TIMESTAMP"))

    return sql.SQL(
        """
        INSERT INTO {table} ({columns})
        VALUES ({values})
        ON CONFLICT ({conflict_columns})
        DO UPDATE SET {assignments}
        RETURNING {primary_key}
        """
    ).format(
        table=sql.Identifier(config.table),
        columns=sql.SQL(", ").join(map(sql.Identifier, config.columns)),
        values=sql.SQL(", ").join(sql.Placeholder() for _ in config.columns),
        conflict_columns=sql.SQL(", ").join(
            map(sql.Identifier, config.conflict_columns)
        ),
        assignments=sql.SQL(", ").join(assignments),
        primary_key=sql.Identifier(config.primary_key),
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
            loaded = load_all(database, args.data_dir)
            for table, row_count in loaded.items():
                print(f"Loaded {row_count} rows into {table}.")


if __name__ == "__main__":
    main()
