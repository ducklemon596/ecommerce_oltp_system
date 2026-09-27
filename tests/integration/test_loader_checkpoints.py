"""Production-like loader integration tests in an isolated PostgreSQL schema."""

from __future__ import annotations

import csv
import shutil
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path
from unittest.mock import patch

import psycopg2

from ecommerce_oltp_system.loader.pipeline import (
    ORDER_LOAD,
    TABLE_LOADS,
    CheckpointMismatchError,
    TableLoadError,
    apply_schema,
    database_config,
    load_large_part,
    load_table,
)


class LoaderCheckpointIntegrationTests(unittest.TestCase):
    """Exercise transaction, checkpoint, constraint, and resume behavior."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create the isolated PostgreSQL schema for this test class."""
        try:
            settings = database_config(Path("database.ini"), "postgresql")
            cls.schema = f"loader_test_{uuid.uuid4().hex[:12]}"
            cls.admin = psycopg2.connect(**settings)
            with cls.admin.cursor() as cursor:
                cursor.execute(f"CREATE SCHEMA {cls.schema}")
            cls.admin.commit()
            cls.settings = {**settings, "options": f"-c search_path={cls.schema},public"}
        except psycopg2.OperationalError as error:
            raise unittest.SkipTest(f"PostgreSQL unavailable: {error}") from error

    @classmethod
    def tearDownClass(cls) -> None:
        """Drop the isolated PostgreSQL schema after all tests."""
        with cls.admin.cursor() as cursor:
            cursor.execute(f"DROP SCHEMA IF EXISTS {cls.schema} CASCADE")
        cls.admin.commit()
        cls.admin.close()

    def setUp(self) -> None:
        """Create a clean schema and temporary directory for one test."""
        with self.admin.cursor() as cursor:
            cursor.execute(f"DROP SCHEMA {self.schema} CASCADE")
            cursor.execute(f"CREATE SCHEMA {self.schema}")
        self.admin.commit()
        self.database = psycopg2.connect(**self.settings)
        apply_schema(self.database)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        """Close the test connection and remove temporary files."""
        self.database.close()
        self.temp_dir.cleanup()

    def test_successful_load_creates_checkpoint(self) -> None:
        """Test a successful load commits its data and checkpoint."""
        outcome = load_table(self.database, self._config("brand"), self._brand_csv("brand.csv"))
        self.assertFalse(outcome.skipped)
        self.assertEqual(self._count("brand"), 1)
        self.assertEqual(self._count("load_checkpoint"), 1)

    def test_same_file_is_skipped_after_successful_load(self) -> None:
        """Test an unchanged completed file is skipped."""
        source = self._brand_csv("brand.csv")
        load_table(self.database, self._config("brand"), source)
        self.assertTrue(load_table(self.database, self._config("brand"), source).skipped)

    def test_changed_file_raises_checkpoint_mismatch(self) -> None:
        """Test changed contents under the same name fail clearly."""
        source = self._brand_csv("brand.csv")
        load_table(self.database, self._config("brand"), source)
        with self.assertRaises(CheckpointMismatchError):
            load_table(self.database, self._config("brand"), self._brand_csv("changed/brand.csv", "Changed"))

    def test_failure_before_checkpoint_rolls_back_data_and_checkpoint(self) -> None:
        """Test an interruption before checkpoint insertion rolls back all work."""
        with patch("ecommerce_oltp_system.loader.strategies.small_table.write_checkpoint", side_effect=RuntimeError("interrupt")):
            with self.assertRaises(TableLoadError):
                load_table(self.database, self._config("brand"), self._brand_csv("brand.csv"))
        self.assertEqual(self._count("brand"), 0)
        self.assertEqual(self._count("load_checkpoint"), 0)

    def test_restart_after_failed_load_retries_successfully(self) -> None:
        """Test a file without a checkpoint can be loaded after failure."""
        source = self._brand_csv("brand.csv")
        with patch("ecommerce_oltp_system.loader.strategies.small_table.write_checkpoint", side_effect=RuntimeError("interrupt")):
            with self.assertRaises(TableLoadError):
                load_table(self.database, self._config("brand"), source)
        self.assertFalse(load_table(self.database, self._config("brand"), source).skipped)

    def test_committed_checkpoint_is_detected_after_restart(self) -> None:
        """Test a post-commit process restart sees the checkpoint."""
        source = self._brand_csv("brand.csv")
        load_table(self.database, self._config("brand"), source)
        restarted = psycopg2.connect(**self.settings)
        try:
            self.assertTrue(load_table(restarted, self._config("brand"), source).skipped)
        finally:
            restarted.close()

    def test_concurrent_same_file_loads_only_once(self) -> None:
        """Test concurrent load attempts commit one file transaction only."""
        source, barrier = self._brand_csv("brand.csv"), Barrier(2)
        module = __import__("ecommerce_oltp_system.loader.strategies.small_table", fromlist=["read_checkpoint"])
        original = module.read_checkpoint
        def synchronized_checkpoint(*args, **kwargs):
            """Synchronize the two initial checkpoint reads."""
            result = original(*args, **kwargs)
            barrier.wait(timeout=5)
            return result
        def attempt():
            """Load the shared source on an independent connection."""
            database = psycopg2.connect(**self.settings)
            try:
                return load_table(database, self._config("brand"), source)
            finally:
                database.close()
        with patch("ecommerce_oltp_system.loader.strategies.small_table.read_checkpoint", side_effect=synchronized_checkpoint):
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(lambda _: attempt(), range(2)))
        self.assertEqual(self._count("brand"), 1)
        self.assertEqual(sorted(result.skipped for result in outcomes), [False, True])

    def test_upsert_updates_existing_business_key(self) -> None:
        """Test a second source file updates an existing business key."""
        load_table(self.database, self._config("brand"), self._brand_csv("brand.csv", "Vietnam"))
        load_table(self.database, self._config("brand"), self._brand_csv("second.csv", "Japan"))
        with self.database.cursor() as cursor:
            cursor.execute("SELECT country FROM brand WHERE brand_code = 'BRD-00001'")
            self.assertEqual(cursor.fetchone()[0], "Japan")
        self.database.commit()

    def test_malformed_csv_fails_without_modifying_existing_data(self) -> None:
        """Test malformed CSV headers fail before modifying prior data."""
        load_table(self.database, self._config("brand"), self._brand_csv("brand.csv"))
        malformed = self.root / "malformed.csv"
        malformed.write_text("brand_code,brand_name\nBRD-00002,Broken\n")
        with self.assertRaises(TableLoadError):
            load_table(self.database, self._config("brand"), malformed)
        self.assertEqual(self._count("brand"), 1)

    def test_check_constraint_violation_rolls_back(self) -> None:
        """Test a database CHECK violation rolls back the file transaction."""
        with self.assertRaises(TableLoadError):
            load_table(self.database, self._config("seller"), self._seller_csv("seller.csv", "9.9"))
        self.assertEqual(self._count("seller"), 0)

    def test_large_part_cleans_staging_before_load(self) -> None:
        """Test stale staging rows cannot affect the next part."""
        self._seed_order_parent()
        load_large_part(self.database, ORDER_LOAD, self._order_csv("order_part_0001.csv", "ORD-000000001"))
        with self.database.cursor() as cursor:
            cursor.execute("INSERT INTO staging_order (order_code, customer_id) VALUES ('STALE', 1)")
        self.database.commit()
        load_large_part(self.database, ORDER_LOAD, self._order_csv("order_part_0002.csv", "ORD-000000002"))
        self.assertEqual(self._count("staging_order"), 0)

    def test_large_part_skips_completed_part(self) -> None:
        """Test a completed large part is skipped on resume."""
        self._seed_order_parent()
        source = self._order_csv("order_part_0001.csv", "ORD-000000001")
        load_large_part(self.database, ORDER_LOAD, source)
        self.assertTrue(load_large_part(self.database, ORDER_LOAD, source).skipped)

    def test_large_part_retry_resynchronizes_sequence(self) -> None:
        """Test a failed large part retries with the expected serial ID."""
        self._seed_order_parent()
        source = self._order_csv("order_part_0001.csv", "ORD-000000001")
        with patch("ecommerce_oltp_system.loader.strategies.large_part.write_checkpoint", side_effect=RuntimeError("interrupt")):
            with self.assertRaises(TableLoadError):
                load_large_part(self.database, ORDER_LOAD, source)
        self.assertEqual(self._count('"order"'), 0)
        self.assertFalse(load_large_part(self.database, ORDER_LOAD, source).skipped)
        with self.database.cursor() as cursor:
            cursor.execute('SELECT order_id FROM "order"')
            self.assertEqual(cursor.fetchone()[0], 1)
        self.database.commit()

    def test_fk_violation_rolls_back(self) -> None:
        """Test an invalid product foreign key rolls back the file transaction."""
        with self.database.cursor() as cursor:
            cursor.execute("INSERT INTO brand (brand_code, brand_name, country, created_at, created_by) VALUES ('BRD-1', 'Brand', 'VN', '2024-12-01', 'test')")
            cursor.execute("INSERT INTO category (category_code, category_name, level, created_at, created_by) VALUES ('CAT-1', 'Category', 1, '2024-12-01', 'test')")
            cursor.execute("INSERT INTO seller (seller_code, seller_name, join_date, created_at, seller_type, rating, country, created_by) VALUES ('SEL-1', 'Seller', '2024-12-01', '2024-12-01', 'Official', 4.0, 'Vietnam', 'test')")
        self.database.commit()
        config = self._config("product")
        source = self._csv("product.csv", config.csv_columns, [["PRD-1", "Product", 999, 1, 1, "10.00", 1, "4.0", "2025-01-01", "true", "test", "", "", "", "", "false", ""]])
        with self.assertRaises(TableLoadError):
            load_table(self.database, config, source)
        self.assertEqual(self._count("product"), 0)
        self.assertEqual(self._count("load_checkpoint"), 0)

    def _config(self, table: str):
        """Return loader metadata for one table."""
        return next(item for item in TABLE_LOADS if item.table == table)

    def _brand_csv(self, name: str, country: str = "Vietnam") -> Path:
        """Create one minimal brand CSV fixture."""
        return self._csv(
            name, self._config("brand").csv_columns,
            [["BRD-00001", "Brand One", country, "2024-12-01 00:00:00", "test", "", "", "", "", "false", ""]],
        )

    def _seller_csv(self, name: str, rating: str) -> Path:
        """Create one minimal seller CSV fixture."""
        return self._csv(
            name, self._config("seller").csv_columns,
            [["SEL-00001", "Seller", "2024-12-01", "2024-12-01 00:00:00", "Official", rating, "Vietnam", "test", "", "", "", "", "false", ""]],
        )

    def _order_csv(self, name: str, code: str) -> Path:
        """Create one minimal order-part CSV fixture."""
        return self._csv(
            name, ORDER_LOAD.columns,
            [[1, code, "2025-01-01 00:00:00", "PAID", "10.00", "2025-01-01 00:00:01", "test", "", "", "", "", "false", ""]],
        )

    def _csv(self, name: str, header, rows) -> Path:
        """Write a CSV fixture with the supplied header and rows."""
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow(header)
            writer.writerows(rows)
        return path

    def _seed_order_parent(self) -> None:
        """Insert the required customer parent for order tests."""
        with self.database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO customer (customer_code, customer_name, email, phone, gender, address, city, created_at, created_by) VALUES ('CUS-1', 'Test', 'test@example.com', '0900000000', 'Male', 'Address', 'City', '2025-01-01', 'test')"
            )
        self.database.commit()

    def _clear(self, *tables: str) -> None:
        """Truncate test tables and reset their identities."""
        with self.database.cursor() as cursor:
            cursor.execute("TRUNCATE TABLE " + ", ".join(tables) + " RESTART IDENTITY CASCADE")
        self.database.commit()

    def _count(self, table: str) -> int:
        """Return the row count for one test table."""
        with self.database.cursor() as cursor:
            cursor.execute(f"SELECT count(*) FROM {table}")
            value = cursor.fetchone()[0]
        self.database.commit()
        return value
