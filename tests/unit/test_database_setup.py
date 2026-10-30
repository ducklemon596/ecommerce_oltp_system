"""Explicit setup and category exports must preserve SQL and data boundaries."""

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

from ecommerce_oltp_system import database_setup
from ecommerce_oltp_system.cli import main
from ecommerce_oltp_system.reporting import GROUPS
from tests.reporting_support import ROOT


class DatabaseSetupTests(unittest.TestCase):
    def test_only_recommended_definitions_are_selected_verbatim(self):
        source = (ROOT / "database/indexes.sql").read_text()
        selected = database_setup.recommended_index_sql(ROOT / "database")
        self.assertEqual(len(selected), 2)
        for name, statement in zip(database_setup.RECOMMENDED_INDEXES, selected):
            self.assertIn(statement, source)
            self.assertIn(name, statement)
            self.assertNotIn("CONCURRENTLY", statement)

    def test_none_installs_functions_without_optional_ddl_or_drops(self):
        database = MagicMock()
        with patch.object(database_setup, "apply_schema") as schema, redirect_stdout(io.StringIO()):
            database_setup.prepare_database(database, ROOT / "database", "none")
        schema.assert_called_once_with(database)
        calls = database.cursor.return_value.__enter__.return_value.execute.call_args_list
        self.assertEqual([c.args[0] for c in calls], [(ROOT / "database/reporting/functions.sql").read_text()])

    def test_failed_setup_exits_transaction_with_error(self):
        database = MagicMock()
        database.cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError("DDL failed")
        with self.assertRaisesRegex(RuntimeError, "DDL failed"):
            database_setup.prepare_database(database, ROOT / "database", "recommended", schema=False)
        self.assertIs(database.__exit__.call_args.args[0], RuntimeError)

    def test_load_prepares_only_after_successful_ingestion(self):
        for failure in (False, True):
            with self.subTest(failure=failure):
                database = MagicMock()
                with patch("ecommerce_oltp_system.loader.pipeline.psycopg2.connect", return_value=database), \
                     patch("ecommerce_oltp_system.loader.pipeline.database_config", return_value={}), \
                     patch("ecommerce_oltp_system.loader.pipeline.validate_source_paths"), \
                     patch("ecommerce_oltp_system.loader.pipeline.apply_schema"), \
                     patch("ecommerce_oltp_system.loader.pipeline.load_all", side_effect=RuntimeError("load failed") if failure else None, return_value={"order": 1}), \
                     patch.object(database_setup, "prepare_database") as prepare, redirect_stdout(io.StringIO()):
                    if failure:
                        with self.assertRaisesRegex(RuntimeError, "load failed"):
                            main(["load", "--indexes", "recommended"])
                        prepare.assert_not_called()
                    else:
                        main(["load", "--indexes", "recommended"])
                        prepare.assert_called_once_with(database, Path("database"), "recommended", schema=False,
                                                        prepared=database_setup.read_setup_sql(ROOT / "database", "recommended"))
                    database.close.assert_called_once()

    @patch("ecommerce_oltp_system.reporting.run")
    def test_groups_dispatch_each_function_once_into_category_directory(self, run):
        for group, names in GROUPS.items():
            with self.subTest(group=group):
                run.reset_mock()
                main(["report", group, "--output-dir", "reports/results"])
                self.assertEqual({c.args[0].report.name for c in run.call_args_list}, set(names))
                self.assertEqual(run.call_count, len(names))
                for call in run.call_args_list:
                    self.assertEqual(call.args[0].output_dir, Path("reports/results") / group)

    @patch("ecommerce_oltp_system.reporting.run")
    def test_drill_down_preserves_supported_filters_and_top(self, run):
        main(["report", "drill-down", "--sellers", "1,2", "--categories", "6", "--top", "3"])
        for call in run.call_args_list:
            args = call.args[0]
            if "sellers" in args.report.filters:
                self.assertEqual(args.sellers, [1, 2])
            if "categories" in args.report.filters:
                self.assertEqual(args.categories, [6])
            if args.report.top_default is not None:
                self.assertEqual(args.top, 3)
