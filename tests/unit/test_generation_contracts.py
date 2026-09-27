"""Fast generator contract tests, including streamed order CSV parts."""

from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from ecommerce_oltp_system.generators.orders.models import ORDER_COLUMNS, ORDER_ITEM_COLUMNS
from ecommerce_oltp_system.generators.pipeline import (
    generate_all_files,
    generate_and_write_data,
)


class GenerationContractTests(unittest.TestCase):
    """Validate output contracts without generating the production-scale dataset."""

    def test_order_part_csv_headers_match_contract(self) -> None:
        """Test streamed CSV headers match the order schemas."""
        output, _, _ = self._generate_order_parts()
        self.assertEqual(self._headers(output, "orders"), ORDER_COLUMNS)
        self.assertEqual(self._headers(output, "order_items"), ORDER_ITEM_COLUMNS)

    def test_order_codes_are_continuous_across_parts(self) -> None:
        """Test order codes remain continuous across part boundaries."""
        orders, _ = self._read_order_parts()
        for expected_id, order in enumerate(orders, start=1):
            self.assertEqual(order["order_code"], f"ORD-{expected_id:09d}")

    def test_order_item_subtotals_match_quantity_and_unit_price(self) -> None:
        """Test every order item has a valid calculated subtotal."""
        _, items = self._read_order_parts()
        for item in items:
            self.assertGreater(int(item["quantity"]), 0)
            self.assertEqual(Decimal(item["subtotal"]), Decimal(item["unit_price"]) * Decimal(item["quantity"]))

    def test_order_item_timestamps_follow_order_dates(self) -> None:
        """Test order-item audit timestamps do not predate order dates."""
        _, items = self._read_order_parts()
        for item in items:
            self.assertLessEqual(datetime.fromisoformat(item["order_date"]), datetime.fromisoformat(item["created_at"]))

    def test_order_totals_equal_item_subtotals(self) -> None:
        """Test every order total equals its item subtotal sum."""
        orders, items = self._read_order_parts()
        totals: dict[int, Decimal] = {}
        for item in items:
            order_id = int(item["order_id"])
            totals[order_id] = totals.get(order_id, Decimal("0")) + Decimal(item["subtotal"])
        for expected_id, order in enumerate(orders, start=1):
            self.assertEqual(Decimal(order["total_amount"]), totals[expected_id])

    def test_order_timestamps_follow_order_dates(self) -> None:
        """Test order audit timestamps do not predate order dates."""
        orders, _ = self._read_order_parts()
        for order in orders:
            self.assertLessEqual(datetime.fromisoformat(order["order_date"]), datetime.fromisoformat(order["created_at"]))

    def _generate_order_parts(self):
        """Generate a compact deterministic set of streamed order parts."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        output = Path(directory.name)
        _, paths, stats = generate_all_files(output_dir=output, order_count=12, orders_per_file=5, show_progress=False)
        self.assertEqual(stats.orders, 12)
        return output, paths, stats

    def _read_order_parts(self):
        """Return all compact generated order and item rows in part order."""
        output, _, _ = self._generate_order_parts()
        orders, items = [], []
        for path in sorted((output / "orders").glob("*.csv")):
            with path.open(newline="", encoding="utf-8") as source:
                orders.extend(csv.DictReader(source))
        for path in sorted((output / "order_items").glob("*.csv")):
            with path.open(newline="", encoding="utf-8") as source:
                items.extend(csv.DictReader(source))
        return orders, items

    def _headers(self, output: Path, directory: str):
        """Return the header from the first generated part in a directory."""
        path = next((output / directory).glob("*.csv"))
        with path.open(newline="", encoding="utf-8") as source:
            return tuple(csv.DictReader(source).fieldnames or ())

    def test_validation_failure_prevents_reference_file_writes(self) -> None:
        """Test validation failure prevents reference file writes."""
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "ecommerce_oltp_system.generators.pipeline.validate_brands",
                side_effect=AssertionError("invalid test data"),
            ):
                with self.assertRaisesRegex(AssertionError, "invalid test data"):
                    generate_and_write_data(output_dir=directory)
            self.assertEqual(list(Path(directory).iterdir()), [])
