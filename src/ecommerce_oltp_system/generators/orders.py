"""Streaming CSV generation for benchmark-scale orders and order items."""

from __future__ import annotations

import argparse
import csv
import random
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from time import perf_counter

from ecommerce_oltp_system.constants import (
    CREATED_BY,
    MAX_ORDER_ITEM_QUANTITY,
    MAX_ORDER_ITEMS,
    MIN_ORDER_ITEMS,
    ORDER_COUNT,
    ORDER_STATUSES,
    ORDERS_PER_FILE,
    PRODUCT_STOCK_RESERVE,
    SEED,
    WINDOW_END,
)
from ecommerce_oltp_system.exporter import csv_value
from ecommerce_oltp_system.models import Record
from ecommerce_oltp_system.validators import validate_order, validate_order_items


ORDER_COLUMNS = (
    "customer_id",
    "order_date",
    "status",
    "total_amount",
    "created_at",
    "created_by",
    "updated_at",
    "updated_by",
    "deleted_at",
    "deleted_by",
    "is_deleted",
    "loaded_at",
)

ORDER_ITEM_COLUMNS = (
    "order_id",
    "product_id",
    "order_date",
    "quantity",
    "unit_price",
    "subtotal",
    "created_at",
    "created_by",
    "updated_at",
    "updated_by",
    "deleted_at",
    "deleted_by",
    "is_deleted",
    "loaded_at",
)


@dataclass(frozen=True, slots=True)
class CustomerReference:
    """Customer fields needed while generating an order."""

    customer_id: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ProductReference:
    """Product fields needed while generating an order item."""

    product_id: int
    created_at: datetime
    price: Decimal
    stock_qty: int


@dataclass(frozen=True, slots=True)
class OrderGenerationStats:
    """Aggregate timing and output counts from one generation run."""

    orders: int
    order_items: int
    elapsed_seconds: float
    order_files: int
    order_item_files: int

    @property
    def orders_per_second(self) -> float:
        return self.orders / self.elapsed_seconds if self.elapsed_seconds else 0.0

    @property
    def order_items_per_second(self) -> float:
        return (
            self.order_items / self.elapsed_seconds if self.elapsed_seconds else 0.0
        )


def generate_order_files(
    data_dir: str | Path = "data",
    output_dir: str | Path | None = None,
    order_count: int = ORDER_COUNT,
    orders_per_file: int = ORDERS_PER_FILE,
    seed: int = SEED,
    show_progress: bool = True,
) -> OrderGenerationStats:
    """Stream orders and items into paired part files without retaining the dataset."""

    if order_count <= 0:
        raise ValueError("order_count must be positive")
    if orders_per_file <= 0:
        raise ValueError("orders_per_file must be positive")

    started_at = perf_counter()
    source_dir = Path(data_dir)
    destination = Path(output_dir) if output_dir is not None else source_dir
    customers = load_customer_references(source_dir / "customer.csv")
    products = load_product_references(source_dir / "product.csv")
    if not customers:
        raise ValueError("customer.csv does not contain any customers")

    available_products = sorted(
        (
            product
            for product in products
            if product.stock_qty > PRODUCT_STOCK_RESERVE
        ),
        key=lambda product: (product.created_at, product.product_id),
    )
    if len(available_products) < MAX_ORDER_ITEMS:
        raise ValueError(
            f"At least {MAX_ORDER_ITEMS} products above the stock reserve are required"
        )

    product_created_at = [product.created_at for product in available_products]
    earliest_fully_eligible_date = product_created_at[MAX_ORDER_ITEMS - 1]
    if earliest_fully_eligible_date > WINDOW_END:
        raise ValueError("Not enough products are available inside the project window")

    remaining_stock = [0] * (max(product.product_id for product in products) + 1)
    for product in available_products:
        remaining_stock[product.product_id] = product.stock_qty
    product_validation_records: dict[int, Record] = {
        product.product_id: {
            "created_at": product.created_at,
            "price": product.price,
            "stock_qty": product.stock_qty,
        }
        for product in available_products
    }

    order_dir = destination / "orders"
    order_item_dir = destination / "order_items"
    order_dir.mkdir(parents=True, exist_ok=True)
    order_item_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    total_items = 0
    generated_orders = 0
    part_number = 0

    while generated_orders < order_count:
        part_number += 1
        part_order_count = min(orders_per_file, order_count - generated_orders)
        first_expected_order_id = generated_orders + 1
        part_started_at = perf_counter()
        part_item_count = _write_part(
            rng=rng,
            customers=customers,
            products=available_products,
            product_created_at=product_created_at,
            remaining_stock=remaining_stock,
            earliest_fully_eligible_date=earliest_fully_eligible_date,
            product_validation_records=product_validation_records,
            first_expected_order_id=first_expected_order_id,
            order_count=part_order_count,
            order_path=order_dir / f"order_part_{part_number:04d}.csv",
            order_item_path=(
                order_item_dir / f"order_item_part_{part_number:04d}.csv"
            ),
        )
        generated_orders += part_order_count
        total_items += part_item_count

        if show_progress:
            _print_part_progress(
                part_number,
                part_order_count,
                part_item_count,
                perf_counter() - part_started_at,
            )

    elapsed_seconds = perf_counter() - started_at
    return OrderGenerationStats(
        orders=generated_orders,
        order_items=total_items,
        elapsed_seconds=elapsed_seconds,
        order_files=part_number,
        order_item_files=part_number,
    )


def load_customer_references(csv_path: str | Path) -> list[CustomerReference]:
    """Read only the expected ID and creation timestamp for each customer."""

    path = Path(csv_path)
    with path.open("r", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        _require_columns(path, reader.fieldnames, {"created_at"})
        return [
            CustomerReference(
                customer_id=customer_id,
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for customer_id, row in enumerate(reader, start=1)
        ]


def load_product_references(csv_path: str | Path) -> list[ProductReference]:
    """Read only fields required for product eligibility and line pricing."""

    path = Path(csv_path)
    with path.open("r", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        _require_columns(
            path,
            reader.fieldnames,
            {"created_at", "price", "stock_qty"},
        )
        return [
            ProductReference(
                product_id=product_id,
                created_at=datetime.fromisoformat(row["created_at"]),
                price=Decimal(row["price"]),
                stock_qty=int(row["stock_qty"]),
            )
            for product_id, row in enumerate(reader, start=1)
        ]


def _write_part(
    *,
    rng: random.Random,
    customers: list[CustomerReference],
    products: list[ProductReference],
    product_created_at: list[datetime],
    remaining_stock: list[int],
    earliest_fully_eligible_date: datetime,
    product_validation_records: dict[int, Record],
    first_expected_order_id: int,
    order_count: int,
    order_path: Path,
    order_item_path: Path,
) -> int:
    part_item_count = 0

    with (
        order_path.open(
            "w", encoding="utf-8", newline="", buffering=1024 * 1024
        ) as order_file,
        order_item_path.open(
            "w", encoding="utf-8", newline="", buffering=1024 * 1024
        ) as order_item_file,
    ):
        order_writer = csv.writer(order_file, lineterminator="\n")
        order_item_writer = csv.writer(order_item_file, lineterminator="\n")
        order_writer.writerow(ORDER_COLUMNS)
        order_item_writer.writerow(ORDER_ITEM_COLUMNS)

        final_expected_order_id = first_expected_order_id + order_count
        for expected_order_id in range(
            first_expected_order_id, final_expected_order_id
        ):
            customer = customers[rng.randrange(len(customers))]
            earliest_order_date = max(
                customer.created_at, earliest_fully_eligible_date
            )
            order_date = _random_datetime(rng, earliest_order_date, WINDOW_END)
            eligible_product_count = bisect_right(product_created_at, order_date)
            item_count = rng.randint(MIN_ORDER_ITEMS, MAX_ORDER_ITEMS)
            selected_indices = rng.sample(range(eligible_product_count), item_count)

            item_records: list[Record] = []
            total_amount = Decimal("0")
            for product_index in selected_indices:
                product = products[product_index]
                quantity = _take_stock_quantity(rng, product, remaining_stock)
                subtotal = product.price * quantity
                total_amount += subtotal
                item_records.append(
                    {
                        "order_id": expected_order_id,
                        "product_id": product.product_id,
                        "order_date": order_date,
                        "quantity": quantity,
                        "unit_price": product.price,
                        "subtotal": subtotal,
                        **_audit_fields(
                            _random_datetime(rng, order_date, WINDOW_END)
                        ),
                    }
                )

            order_record: Record = {
                "customer_id": customer.customer_id,
                "order_date": order_date,
                "status": rng.choice(ORDER_STATUSES),
                "total_amount": total_amount,
                **_audit_fields(_random_datetime(rng, order_date, WINDOW_END)),
            }
            validate_order_items(
                item_records,
                expected_order_id,
                order_date,
                product_validation_records,
                remaining_stock,
            )
            validate_order(order_record, item_records, customer.created_at)

            order_writer.writerow(_csv_row(order_record, ORDER_COLUMNS))
            order_item_writer.writerows(
                _csv_row(item, ORDER_ITEM_COLUMNS) for item in item_records
            )
            part_item_count += item_count

    return part_item_count


def _take_stock_quantity(
    rng: random.Random,
    product: ProductReference,
    remaining_stock: list[int],
) -> int:
    """Take units while retaining safety stock, replenishing when required."""

    product_stock = remaining_stock[product.product_id]
    if product_stock <= PRODUCT_STOCK_RESERVE:
        product_stock = product.stock_qty

    quantity = rng.randint(
        1,
        min(
            MAX_ORDER_ITEM_QUANTITY,
            product_stock - PRODUCT_STOCK_RESERVE,
        ),
    )
    remaining_stock[product.product_id] = product_stock - quantity
    return quantity


def _audit_fields(created_at: datetime) -> Record:
    return {
        "created_at": created_at,
        "created_by": CREATED_BY,
        "updated_at": None,
        "updated_by": None,
        "deleted_at": None,
        "deleted_by": None,
        "is_deleted": False,
        "loaded_at": None,
    }


def _csv_row(record: Record, columns: tuple[str, ...]) -> tuple[object, ...]:
    return tuple(csv_value(record[column]) for column in columns)


def _random_datetime(
    rng: random.Random, start_datetime: datetime, end_datetime: datetime
) -> datetime:
    seconds = int((end_datetime - start_datetime).total_seconds())
    if seconds < 0:
        raise ValueError("Cannot generate a datetime before its lower bound")
    return start_datetime + timedelta(seconds=rng.randint(0, seconds))


def _require_columns(
    path: Path, fieldnames: list[str] | None, required: set[str]
) -> None:
    available = set(fieldnames or ())
    missing = sorted(required - available)
    if missing:
        raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")


def _print_part_progress(
    part_number: int,
    order_count: int,
    order_item_count: int,
    elapsed_seconds: float,
) -> None:
    print(
        f"Part {part_number}:\n"
        f"{order_count:,} orders\n"
        f"{order_item_count:,} order items\n"
        f"elapsed: {elapsed_seconds:.2f}s\n"
        f"orders/sec: {_rate(order_count, elapsed_seconds):,.2f}\n"
        f"order_items/sec: {_rate(order_item_count, elapsed_seconds):,.2f}",
        flush=True,
    )


def print_summary(stats: OrderGenerationStats) -> None:
    """Print lightweight aggregate benchmark results."""

    print(
        "Complete:\n"
        f"total orders generated: {stats.orders:,}\n"
        f"total order items generated: {stats.order_items:,}\n"
        f"total elapsed time: {stats.elapsed_seconds:.2f}s\n"
        f"orders/second: {stats.orders_per_second:,.2f}\n"
        f"order_items/second: {stats.order_items_per_second:,.2f}\n"
        f"number of order files: {stats.order_files}\n"
        f"number of order_item files: {stats.order_item_files}"
    )


def _rate(row_count: int, elapsed_seconds: float) -> float:
    return row_count / elapsed_seconds if elapsed_seconds else 0.0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stream benchmark-scale order and order-item CSV files."
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output root; defaults to --data-dir.",
    )
    parser.add_argument("--orders", type=int, default=ORDER_COUNT)
    parser.add_argument("--orders-per-file", type=int, default=ORDERS_PER_FILE)
    parser.add_argument("--seed", type=int, default=SEED)
    return parser.parse_args()


def main() -> None:
    """Command-line entry point for streaming order generation."""

    args = _arguments()
    stats = generate_order_files(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        order_count=args.orders,
        orders_per_file=args.orders_per_file,
        seed=args.seed,
    )
    print_summary(stats)


if __name__ == "__main__":
    main()
