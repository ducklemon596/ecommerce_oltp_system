"""Input failures must be actionable and precede mutating load stages."""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import psycopg2

from ecommerce_oltp_system import database_setup
from ecommerce_oltp_system.cli import main
from ecommerce_oltp_system.loader import pipeline
from ecommerce_oltp_system.loader.db.connection import database_config
from ecommerce_oltp_system.loader.exceptions import TableLoadError
from ecommerce_oltp_system.reporting import main as report_main
from tests.reporting_support import ROOT


class CliErrorTests(unittest.TestCase):
    def test_missing_config_exits_without_connecting(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = str(Path(directory) / "missing.ini")
            for command in (["init-db"], ["load"], ["setup"], ["report", "monthly"]):
                with self.subTest(command=command), patch("psycopg2.connect") as connect:
                    with self.assertRaisesRegex(SystemExit, "configuration file not found"):
                        main([*command, "--config", missing])
                    connect.assert_not_called()

    def test_invalid_ini_syntax_is_a_configuration_error(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "bad.ini"
            config.write_text("host=localhost\n")
            with self.assertRaisesRegex(ValueError, "Check its INI syntax"):
                database_config(config)

    def test_empty_and_reversed_windows_fail_for_both_entrypoints(self):
        for entrypoint, prefix in ((main, ["report"]), (report_main, [])):
            for target in ("monthly", "all", "drill-down"):
                for end in ("2025-03-01", "2025-02-01"):
                    with self.subTest(target=target, end=end), patch("psycopg2.connect") as connect:
                        with self.assertRaisesRegex(SystemExit, "--start must be earlier"):
                            entrypoint([*prefix, target, "--start", "2025-03-01", "--end", end])
                        connect.assert_not_called()

    def test_missing_or_unpaired_parts_fail_before_any_load_or_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for config in pipeline.TABLE_LOADS:
                (root / f"{config.table}.csv").touch()
            for mismatch in (False, True):
                if mismatch:
                    (root / "orders").mkdir()
                    (root / "order_items").mkdir()
                    (root / "orders/order_part_0001.csv").touch()
                    (root / "order_items/order_item_part_0002.csv").touch()
                with self.subTest(mismatch=mismatch), patch.object(pipeline, "database_config", return_value={}), \
                     patch.object(pipeline, "load_table") as load, patch("psycopg2.connect") as connect:
                    with self.assertRaises(SystemExit):
                        main(["load", "--data-dir", str(root)])
                    connect.assert_not_called()
                    with self.assertRaises((FileNotFoundError, ValueError)):
                        pipeline.load_all(MagicMock(), root)
                    load.assert_not_called()

    def test_missing_setup_assets_fail_before_schema_or_ingestion(self):
        with tempfile.TemporaryDirectory() as directory:
            for command in (["setup"], ["load", "--indexes", "recommended"]):
                with self.subTest(command=command), patch("psycopg2.connect") as connect, \
                     patch.object(pipeline, "database_config", return_value={}), \
                     patch.object(database_setup, "database_config", return_value={}), \
                     patch.object(pipeline, "validate_source_paths"), \
                     patch.object(pipeline, "apply_schema") as schema, patch.object(pipeline, "load_all") as load:
                    with self.assertRaisesRegex(SystemExit, "functions.sql"):
                        main([*command, "--sql-dir", directory])
                    connect.assert_not_called()
                    schema.assert_not_called()
                    load.assert_not_called()

    def test_directory_named_like_csv_part_fails_before_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for config in pipeline.TABLE_LOADS:
                (root / f"{config.table}.csv").touch()
            (root / "orders/order_part_0001.csv").mkdir(parents=True)
            (root / "order_items").mkdir()
            (root / "order_items/order_item_part_0001.csv").touch()
            with patch.object(pipeline, "database_config", return_value={}), patch("psycopg2.connect") as connect:
                with self.assertRaisesRegex(SystemExit, "Expected CSV part files"):
                    main(["load", "--data-dir", str(root)])
                connect.assert_not_called()

    def test_load_failure_names_checkpoint_recovery_and_closes_connection(self):
        database = MagicMock()
        with patch.object(pipeline, "database_config", return_value={}), \
             patch.object(pipeline, "validate_source_paths"), patch.object(pipeline, "apply_schema"), \
             patch("psycopg2.connect", return_value=database), \
             patch.object(pipeline, "load_all", side_effect=TableLoadError("bad CSV")):
            with redirect_stdout(io.StringIO()), self.assertRaisesRegex(SystemExit, "Earlier successful files remain committed"):
                main(["load"])
        database.close.assert_called_once()

    def test_post_load_setup_failure_distinguishes_committed_data(self):
        database = MagicMock()
        with patch.object(pipeline, "database_config", return_value={}), \
             patch.object(pipeline, "validate_source_paths"), patch.object(pipeline, "apply_schema"), \
             patch("psycopg2.connect", return_value=database), \
             patch.object(pipeline, "load_all", return_value={"order": 3}), \
             patch.object(database_setup, "prepare_database", side_effect=psycopg2.OperationalError("setup failed")):
            with redirect_stdout(io.StringIO()), self.assertRaisesRegex(SystemExit, "Data ingestion is already committed"):
                main(["load", "--indexes", "recommended", "--sql-dir", str(ROOT / "database")])
        database.close.assert_called_once()

    def test_preloaded_assets_survive_checkout_removal_during_ingestion(self):
        prepared = database_setup.read_setup_sql(ROOT / "database", "recommended")
        database = MagicMock()
        with patch.object(database_setup, "read_setup_sql", side_effect=FileNotFoundError("removed")):
            with redirect_stdout(io.StringIO()):
                database_setup.prepare_database(database, Path("removed"), "recommended", schema=False, prepared=prepared)
        statements = [call.args[0] for call in database.cursor.return_value.__enter__.return_value.execute.call_args_list]
        self.assertIn(prepared.functions, statements)
        self.assertTrue(all(statement in statements for statement in prepared.indexes))
