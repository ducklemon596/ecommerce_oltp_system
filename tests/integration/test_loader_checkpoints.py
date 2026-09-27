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

from ecommerce_oltp_system.loader.database import (
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
        with cls.admin.cursor() as cursor:
            cursor.execute(f"DROP SCHEMA IF EXISTS {cls.schema} CASCADE")
        cls.admin.commit()
        cls.admin.close()

    def setUp(self) -> None:
        with self.admin.cursor() as cursor:
            cursor.execute(f"DROP SCHEMA {self.schema} CASCADE")
            cursor.execute(f"CREATE SCHEMA {self.schema}")
        self.admin.commit()
        self.database = psycopg2.connect(**self.settings)
        apply_schema(self.database)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.database.close()
        self.temp_dir.cleanup()

    def test_checkpoint_skip_mismatch_rollback_and_restart(self) -> None:
        config = self._config("brand")
        source = self._brand_csv("brand.csv")
        first = load_table(self.database, config, source)
        second = load_table(self.database, config, source)
        self.assertFalse(first.skipped)
        self.assertTrue(second.skipped)
        self.assertEqual(self._count("load_checkpoint"), 1)

        changed = self._brand_csv("changed/brand.csv", country="Changed")
        with self.assertRaises(CheckpointMismatchError):
            load_table(self.database, config, changed)

        self._clear("brand", "load_checkpoint")
        with patch(
            "ecommerce_oltp_system.loader.database._write_checkpoint",
            side_effect=RuntimeError("interrupt before checkpoint"),
        ):
            with self.assertRaises(TableLoadError):
                load_table(self.database, config, source)
        self.assertEqual(self._count("brand"), 0)
        self.assertEqual(self._count("load_checkpoint"), 0)

        restarted = load_table(self.database, config, source)
        self.assertFalse(restarted.skipped)
        self.assertTrue(load_table(self.database, config, source).skipped)

    def test_committed_checkpoint_survives_missing_success_report(self) -> None:
        source = self._brand_csv("brand.csv")
        outcome = load_table(self.database, self._config("brand"), source)
        self.assertFalse(outcome.skipped)
        # Simulates a process dying after commit and before its success message.
        restarted_connection = psycopg2.connect(**self.settings)
        try:
            self.assertTrue(
                load_table(restarted_connection, self._config("brand"), source).skipped
            )
        finally:
            restarted_connection.close()

    def test_concurrent_same_file_loads_once_then_skips(self) -> None:
        source = self._brand_csv("brand.csv")
        barrier = Barrier(2)
        original_checkpoint = __import__(
            "ecommerce_oltp_system.loader.database", fromlist=["_checkpoint"]
        )._checkpoint

        def synchronized_checkpoint(*args, **kwargs):
            result = original_checkpoint(*args, **kwargs)
            barrier.wait(timeout=5)
            return result

        def attempt():
            database = psycopg2.connect(**self.settings)
            try:
                return load_table(database, self._config("brand"), source)
            finally:
                database.close()

        with patch(
            "ecommerce_oltp_system.loader.database._checkpoint",
            side_effect=synchronized_checkpoint,
        ):
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(lambda _: attempt(), range(2)))
        self.assertEqual(self._count("brand"), 1)
        self.assertEqual(self._count("load_checkpoint"), 1)
        self.assertEqual(sorted(result.skipped for result in outcomes), [False, True])

    def test_upsert_constraint_and_header_failures_roll_back(self) -> None:
        brand = self._brand_csv("brand.csv", country="Vietnam")
        load_table(self.database, self._config("brand"), brand)
        update = self._brand_csv("second.csv", country="Japan")
        load_table(self.database, self._config("brand"), update)
        with self.database.cursor() as cursor:
            cursor.execute("SELECT country FROM brand WHERE brand_code = 'BRD-00001'")
            self.assertEqual(cursor.fetchone()[0], "Japan")
        self.database.commit()

        malformed = self.root / "malformed.csv"
        malformed.write_text("brand_code,brand_name\nBRD-00002,Broken\n")
        with self.assertRaises(TableLoadError):
            load_table(self.database, self._config("brand"), malformed)
        self.assertEqual(self._count("brand"), 1)

        invalid = self._seller_csv("seller.csv", rating="9.9")
        with self.assertRaises(TableLoadError):
            load_table(self.database, self._config("seller"), invalid)
        self.assertEqual(self._count("seller"), 0)

    def test_large_part_resume_staging_cleanup_and_sequence_retry(self) -> None:
        self._seed_order_parent()
        first = self._order_csv("order_part_0001.csv", "ORD-000000001")
        second = self._order_csv("order_part_0002.csv", "ORD-000000002")
        load_large_part(self.database, ORDER_LOAD, first)
        with self.database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO staging_order (order_code, customer_id) VALUES ('STALE', 1)"
            )
        self.database.commit()
        load_large_part(self.database, ORDER_LOAD, second)
        self.assertEqual(self._count("staging_order"), 0)
        self.assertTrue(load_large_part(self.database, ORDER_LOAD, first).skipped)

        self._clear('"order"', "load_checkpoint")
        with patch(
            "ecommerce_oltp_system.loader.database._write_checkpoint",
            side_effect=RuntimeError("interrupt"),
        ):
            with self.assertRaises(TableLoadError):
                load_large_part(self.database, ORDER_LOAD, first)
        self.assertEqual(self._count('"order"'), 0)
        retried = load_large_part(self.database, ORDER_LOAD, first)
        self.assertFalse(retried.skipped)
        with self.database.cursor() as cursor:
            cursor.execute('SELECT order_id FROM "order"')
            self.assertEqual(cursor.fetchone()[0], 1)
        self.database.commit()

    def test_fk_violation_rolls_back_loader_transaction(self) -> None:
        with self.database.cursor() as cursor:
            cursor.execute("INSERT INTO brand (brand_code, brand_name, country, created_at, created_by) VALUES ('BRD-1', 'Brand', 'VN', '2024-12-01', 'test')")
            cursor.execute("INSERT INTO category (category_code, category_name, level, created_at, created_by) VALUES ('CAT-1', 'Category', 1, '2024-12-01', 'test')")
            cursor.execute("INSERT INTO seller (seller_code, seller_name, join_date, created_at, seller_type, rating, country, created_by) VALUES ('SEL-1', 'Seller', '2024-12-01', '2024-12-01', 'Official', 4.0, 'Vietnam', 'test')")
        self.database.commit()
        config = self._config("product")
        source = self._csv(
            "product.csv", config.csv_columns,
            [["PRD-1", "Product", 999, 1, 1, "10.00", 1, "4.0", "2025-01-01", "true", "test", "", "", "", "", "false", ""]],
        )
        with self.assertRaises(TableLoadError):
            load_table(self.database, config, source)
        self.assertEqual(self._count("product"), 0)
        self.assertEqual(self._count("load_checkpoint"), 0)

    def _config(self, table: str):
        return next(item for item in TABLE_LOADS if item.table == table)

    def _brand_csv(self, name: str, country: str = "Vietnam") -> Path:
        return self._csv(
            name, self._config("brand").csv_columns,
            [["BRD-00001", "Brand One", country, "2024-12-01 00:00:00", "test", "", "", "", "", "false", ""]],
        )

    def _seller_csv(self, name: str, rating: str) -> Path:
        return self._csv(
            name, self._config("seller").csv_columns,
            [["SEL-00001", "Seller", "2024-12-01", "2024-12-01 00:00:00", "Official", rating, "Vietnam", "test", "", "", "", "", "false", ""]],
        )

    def _order_csv(self, name: str, code: str) -> Path:
        return self._csv(
            name, ORDER_LOAD.columns,
            [[1, code, "2025-01-01 00:00:00", "PAID", "10.00", "2025-01-01 00:00:01", "test", "", "", "", "", "false", ""]],
        )

    def _csv(self, name: str, header, rows) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow(header)
            writer.writerows(rows)
        return path

    def _seed_order_parent(self) -> None:
        with self.database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO customer (customer_code, customer_name, email, phone, gender, address, city, created_at, created_by) VALUES ('CUS-1', 'Test', 'test@example.com', '0900000000', 'Male', 'Address', 'City', '2025-01-01', 'test')"
            )
        self.database.commit()

    def _clear(self, *tables: str) -> None:
        with self.database.cursor() as cursor:
            cursor.execute("TRUNCATE TABLE " + ", ".join(tables) + " RESTART IDENTITY CASCADE")
        self.database.commit()

    def _count(self, table: str) -> int:
        with self.database.cursor() as cursor:
            cursor.execute(f"SELECT count(*) FROM {table}")
            value = cursor.fetchone()[0]
        self.database.commit()
        return value
