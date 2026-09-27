"""CSV-header validation and PostgreSQL value conversion helpers."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Callable

from .config import BOOLEAN_COLUMNS, DATE_COLUMNS, DECIMAL_COLUMNS, INTEGER_COLUMNS, TIMESTAMP_COLUMNS
from .models import TableLoad


def validate_header(actual: list[str] | None, config: TableLoad, csv_path: Path) -> None:
    """Validate one reference CSV header before the small-table load transaction.

    The ``execute_values`` strategy supplies the CSV header, table metadata, and
    source path. The function returns ``None`` when the ordered header matches
    the configured contract, otherwise raises before any row is inserted or a
    checkpoint is written.
    """
    expected = list(config.csv_columns)
    if actual != expected:
        raise ValueError(f"Unexpected columns in {csv_path}; expected {expected}, received {actual}")


def parse_value(column: str, value: str) -> object:
    """Convert one small-table CSV field before its parameterized UPSERT.

    Called for each configured database column by the small-table strategy.
    ``column`` selects the project type contract and ``value`` is the raw CSV
    text; the converted Python object or ``None`` is returned for psycopg2. The
    function has no database or file side effects and raises on invalid values.
    """
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
        converter = parse_boolean
    return converter(value) if converter else value


def parse_boolean(value: str) -> bool:
    """Convert strict lowercase/uppercase CSV booleans, rejecting ambiguous values."""
    normalized = value.lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")
