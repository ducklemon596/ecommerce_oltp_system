"""Per-order validation applied before streamed CSV rows are written."""

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal

from ..config import (
    MAX_ORDER_ITEM_QUANTITY,
    MAX_ORDER_ITEMS,
    MIN_ORDER_ITEMS,
    ORDER_STATUSES,
    WINDOW_END,
    WINDOW_START,
)
from ..models import Record
from ..reference.validation import validate_audit_fields


def validate_order(
    order: Record,
    order_items: list[Record],
    customer_created_at: datetime,
) -> None:
    """Validate one streamed order and its calculated total."""

    assert "order_id" not in order, "order_id must remain database-managed"
    validate_audit_fields([order])
    assert order["order_code"].startswith("ORD-"), "Invalid order_code"
    assert order["order_code"][4:].isdigit(), "Invalid order_code"
    assert order["customer_id"] > 0, "Invalid customer_id"
    assert WINDOW_START <= order["order_date"] <= WINDOW_END, (
        "Order date is outside the generation window"
    )
    assert customer_created_at <= order["order_date"], (
        "Order predates its customer"
    )
    assert order["status"] in ORDER_STATUSES, "Invalid order status"
    assert order["created_at"] >= order["order_date"], (
        "Order created_at predates order_date"
    )
    assert order["created_at"] <= WINDOW_END, (
        "Order created_at is outside the generation window"
    )
    expected_total = sum(
        (item["subtotal"] for item in order_items),
        start=Decimal("0"),
    )
    assert order["total_amount"] == expected_total, (
        "Order total does not equal its item subtotals"
    )
    assert order["total_amount"] >= 0, "Order total cannot be negative"


def validate_order_items(
    order_items: list[Record],
    expected_order_id: int,
    order_date: datetime,
    product_references: Mapping[int, Record],
) -> None:
    """Validate the small item collection for one streamed order."""

    assert MIN_ORDER_ITEMS <= len(order_items) <= MAX_ORDER_ITEMS, (
        "An order must contain 2 to 5 items"
    )
    order_item_codes: set[str] = set()
    validate_audit_fields(order_items)
    used_product_ids: set[int] = set()

    for item in order_items:
        assert "order_item_id" not in item, (
            "order_item_id must remain database-managed"
        )
        expected_code_prefix = f"OIT-{expected_order_id:09d}-"
        order_item_code = item["order_item_code"]
        assert order_item_code.startswith(expected_code_prefix), "Invalid order_item_code"
        assert order_item_code[len(expected_code_prefix):].isdigit(), "Invalid order_item_code"
        assert order_item_code not in order_item_codes, "Duplicate order_item_code"
        order_item_codes.add(order_item_code)

        assert item["order_id"] == expected_order_id, (
            "Order item references the wrong expected order_id"
        )
        product_id = item["product_id"]
        assert product_id in product_references, "Invalid product_id"
        assert product_id not in used_product_ids, (
            "Products must be unique within an order"
        )
        used_product_ids.add(product_id)

        product = product_references[product_id]
        assert item["order_date"] == order_date, (
            "Order item order_date differs from its order"
        )
        assert product["created_at"] <= order_date, (
            "Order item predates its product"
        )
        assert 0 < item["quantity"] <= MAX_ORDER_ITEM_QUANTITY, (
            "Order item quantity is outside the allowed range"
        )
        assert item["unit_price"] == product["price"], (
            "Order item unit_price differs from its product price"
        )
        assert item["unit_price"] > 0, "Order item unit_price must be positive"
        assert item["subtotal"] == item["quantity"] * item["unit_price"], (
            "Order item subtotal is incorrect"
        )
        assert item["created_at"] >= order_date, (
            "Order item created_at predates order_date"
        )
        assert item["created_at"] <= WINDOW_END, (
            "Order item created_at is outside the generation window"
        )
