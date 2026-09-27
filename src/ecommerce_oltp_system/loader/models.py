"""Immutable metadata and result objects used by the database loader."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TableLoad:
    """Describe a small or medium CSV table loaded with ``execute_values``.

    The metadata is consumed by the small-table transaction loader to validate
    CSV columns, build its UPSERT, and synchronize its generated primary key.
    """

    table: str
    primary_key: str
    columns: tuple[str, ...]
    conflict_columns: tuple[str, ...]
    requires_positional_ids: bool = False

    @property
    def csv_columns(self) -> tuple[str, ...]:
        """Return the complete source-file header, including ``loaded_at``."""
        return (*self.columns, "loaded_at")


@dataclass(frozen=True)
class LargeTableLoad:
    """Describe a high-volume CSV part loaded through a staging table.

    It is used for ``order`` and ``order_item``.  Final-table constraints stay
    in PostgreSQL while the staging table remains intentionally lightweight.
    """

    table: str
    staging_table: str
    primary_key: str
    columns: tuple[str, ...]
    conflict_columns: tuple[str, ...]
    validate_order_ids: bool = False

    @property
    def final_columns(self) -> tuple[str, ...]:
        """Return source columns written to the final table by the UPSERT."""
        return tuple(column for column in self.columns if column != "loaded_at")


@dataclass(frozen=True)
class LoadOutcome:
    """Report the source row count and whether a checkpoint skipped the load."""

    row_count: int
    skipped: bool = False
