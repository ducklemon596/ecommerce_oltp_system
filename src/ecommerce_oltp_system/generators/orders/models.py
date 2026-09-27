"""Data contracts used while streaming order and order-item CSV parts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


ORDER_COLUMNS = (
    "customer_id", "order_code", "order_date", "status", "total_amount",
    "created_at", "created_by", "updated_at", "updated_by", "deleted_at",
    "deleted_by", "is_deleted", "loaded_at",
)

ORDER_ITEM_COLUMNS = (
    "order_id", "order_item_code", "product_id", "order_date", "quantity",
    "unit_price", "subtotal", "created_at", "created_by", "updated_at",
    "updated_by", "deleted_at", "deleted_by", "is_deleted", "loaded_at",
)


@dataclass(frozen=True, slots=True)
class CustomerReference:
    """The customer data needed to select a temporally eligible order parent."""

    customer_id: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ProductReference:
    """The product fields required for eligibility and order-item pricing."""

    product_id: int
    created_at: datetime
    price: Decimal


@dataclass(frozen=True, slots=True)
class ParetoReferencePool:
    """Creation-time ordered references split into preferential head and tail."""

    records: tuple[CustomerReference | ProductReference, ...]
    record_dates: tuple[datetime, ...]
    head: tuple[CustomerReference | ProductReference, ...]
    head_dates: tuple[datetime, ...]
    tail: tuple[CustomerReference | ProductReference, ...]
    tail_dates: tuple[datetime, ...]


@dataclass(frozen=True, slots=True)
class OrderGenerationStats:
    """Aggregate counts and timings returned after a streamed generation run."""

    orders: int
    order_items: int
    elapsed_seconds: float
    order_files: int
    order_item_files: int

    @property
    def orders_per_second(self) -> float:
        """Return the average streamed order generation rate."""
        return self.orders / self.elapsed_seconds if self.elapsed_seconds else 0.0

    @property
    def order_items_per_second(self) -> float:
        """Return the average streamed order-item generation rate."""
        return self.order_items / self.elapsed_seconds if self.elapsed_seconds else 0.0
