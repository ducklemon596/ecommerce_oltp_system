"""Fast generator contract tests, including streamed order CSV parts."""

from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from ecommerce_oltp_system.generators.orders import ORDER_COLUMNS, ORDER_ITEM_COLUMNS
from ecommerce_oltp_system.generators.pipeline import (
    generate_all_files,
    generate_and_write_data,
)


class GenerationContractTests(unittest.TestCase):
    """Validate output contracts without generating the production-scale dataset."""

    def test_order_parts_are_temporally_valid_and_id_continuous(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            _, _, stats = generate_all_files(
                output_dir=output, order_count=12, orders_per_file=5, show_progress=False
            )
            self.assertEqual(stats.orders, 12)
            orders = []
            items = []
            for path in sorted((output / "orders").glob("*.csv")):
                with path.open(newline="", encoding="utf-8") as source:
                    reader = csv.DictReader(source)
                    self.assertEqual(tuple(reader.fieldnames or ()), ORDER_COLUMNS)
                    orders.extend(reader)
            for path in sorted((output / "order_items").glob("*.csv")):
                with path.open(newline="", encoding="utf-8") as source:
                    reader = csv.DictReader(source)
                    self.assertEqual(tuple(reader.fieldnames or ()), ORDER_ITEM_COLUMNS)
                    items.extend(reader)

            totals: dict[int, Decimal] = {}
            for item in items:
                order_id = int(item["order_id"])
                self.assertGreater(int(item["quantity"]), 0)
                self.assertEqual(
                    Decimal(item["subtotal"]),
                    Decimal(item["unit_price"]) * Decimal(item["quantity"]),
                )
                self.assertLessEqual(
                    datetime.fromisoformat(item["order_date"]),
                    datetime.fromisoformat(item["created_at"]),
                )
                totals[order_id] = totals.get(order_id, Decimal("0")) + Decimal(item["subtotal"])
            for expected_id, order in enumerate(orders, start=1):
                self.assertEqual(order["order_code"], f"ORD-{expected_id:09d}")
                self.assertEqual(Decimal(order["total_amount"]), totals[expected_id])
                self.assertLessEqual(
                    datetime.fromisoformat(order["order_date"]),
                    datetime.fromisoformat(order["created_at"]),
                )

    def test_validation_failure_prevents_reference_file_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "ecommerce_oltp_system.generators.pipeline.validate_brands",
                side_effect=AssertionError("invalid test data"),
            ):
                with self.assertRaisesRegex(AssertionError, "invalid test data"):
                    generate_and_write_data(output_dir=directory)
            self.assertEqual(list(Path(directory).iterdir()), [])
