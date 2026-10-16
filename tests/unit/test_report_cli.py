"""Report catalog, argument parsing, output, and read-only connection contracts."""

import argparse
import csv
import io
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import psycopg2

from ecommerce_oltp_system.cli import main
from ecommerce_oltp_system.reporting import REPORTS, main as report_main, parse_ids, print_table
from tests.reporting_support import function_definitions


class ReportCliTests(unittest.TestCase):
    """Exercise terminal behavior without requiring PostgreSQL."""

    def test_catalog_covers_every_function_and_parameter_in_order(self):
        """Keep CLI metadata in sync with canonical SQL signatures, not SQL logic."""
        definitions = function_definitions()
        self.assertEqual([report.function for report in REPORTS], list(definitions))
        names = {"products": "p_product_ids", "sellers": "p_seller_ids", "categories": "p_category_ids", "brands": "p_brand_ids"}
        for report in REPORTS:
            with self.subTest(report=report.name):
                expected = re.findall(r"\b(p_\w+)\s+(?:DATE|INTEGER(?:\[\])?)", definitions[report.function][0])
                actual = ["p_start_date", "p_end_date", *(names[name] for name in report.filters)]
                if report.top_default is not None:
                    actual.append("p_top_n")
                self.assertEqual(actual, expected)

    def test_null_ids_parse_as_none(self):
        """Explicit NULL and whitespace/case variants disable a filter."""
        for value in ("null", "NULL", " Null "):
            with self.subTest(value=value):
                self.assertIsNone(parse_ids(value))

    def test_empty_ids_parse_as_empty_list(self):
        """An empty argument is not silently treated as a disabled filter."""
        for value in ("", "  ", "[]"):
            with self.subTest(value=value):
                self.assertEqual(parse_ids(value), [])

    def test_multiple_ids_parse_as_integers(self):
        """Comma-separated filters preserve integer values and order."""
        self.assertEqual(parse_ids("2, 10,30"), [2, 10, 30])

    def test_malformed_id_lists_are_rejected(self):
        """Reject non-integer input rather than inserting it into SQL."""
        for value in ("1,,2", "one", "1); DROP TABLE product;--"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                parse_ids(value)

    @patch("ecommerce_oltp_system.reporting.run")
    def test_report_defaults_use_march_and_null_filters(self, run):
        """Defaults demonstrate one month without restricting optional filters."""
        main(["report", "seller-performance"])
        args = run.call_args.args[0]
        self.assertEqual((args.start, args.end, args.limit), (date(2025, 3, 1), date(2025, 4, 1), 50))
        self.assertIsNone(args.brands)
        self.assertIsNone(args.categories)

    @patch("ecommerce_oltp_system.reporting.run")
    def test_report_forwards_typed_parameters_and_connection_options(self, run):
        """Keep empty categories, multiple brands, and INI selection distinct."""
        main(["report", "seller-performance", "--start", "2025-01-01", "--end", "2025-06-01", "--brands", "2,10,30", "--categories", "", "--config", "test.ini", "--section", "test"])
        args = run.call_args.args[0]
        self.assertEqual((args.start, args.end, args.brands, args.categories, args.config, args.section), (date(2025, 1, 1), date(2025, 6, 1), [2, 10, 30], [], Path("test.ini"), "test"))

    @patch("ecommerce_oltp_system.reporting.run")
    def test_top_n_is_independent_of_export_limit(self, run):
        """The CSV row limit must not replace the function's ranking parameter."""
        main(["report", "top-products", "--top", "10", "--limit", "3"])
        args = run.call_args.args[0]
        self.assertEqual((args.top, args.limit), (10, 3))

    def test_only_applicable_filters_are_accepted(self):
        """Do not advertise seller filtering on a monthly platform aggregate."""
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            main(["report", "monthly", "--sellers", "1"])
        self.assertEqual(error.exception.code, 2)

    def test_invalid_dates_fail_before_database_access(self):
        """Reject invalid calendar dates during argparse conversion."""
        with patch("ecommerce_oltp_system.reporting.psycopg2.connect") as connect:
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(["report", "monthly", "--start", "2025-02-30"])
            connect.assert_not_called()

    def test_nonpositive_export_limit_is_rejected(self):
        """Keep CSV fetch bounds positive."""
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["report", "monthly", "--limit", "0"])

    def test_list_requires_no_database_or_config(self):
        """Discovery/help must work before database setup."""
        output = io.StringIO()
        with patch("ecommerce_oltp_system.reporting.database_config") as config, redirect_stdout(output):
            main(["report", "list"])
        config.assert_not_called()
        for report in REPORTS:
            self.assertIn(report.name, output.getvalue())

    def test_empty_result_still_prints_column_headers(self):
        """Zero matching rows produce a readable table, not a formatter failure."""
        output = io.StringIO()
        with redirect_stdout(output):
            print_table(("month", "total_revenue"), [])
        self.assertIn("total_revenue", output.getvalue())

    @patch("ecommerce_oltp_system.reporting.database_config", return_value={})
    @patch("ecommerce_oltp_system.reporting.execute_report", return_value=(("month",), []))
    def test_reporting_connection_is_read_only_and_closed(self, _execute, _config):
        """Reporting transactions cannot write, and their connection is released."""
        database = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            with patch("ecommerce_oltp_system.reporting.psycopg2.connect", return_value=database), redirect_stdout(io.StringIO()):
                main(["report", "monthly", "--output-dir", directory])
        database.set_session.assert_called_once_with(readonly=True)
        database.close.assert_called_once()

    @patch("ecommerce_oltp_system.reporting.run")
    def test_bare_shortcut_runs_all_reports(self, run):
        """The new report shortcut defaults to all 12 functions, in catalog order."""
        report_main([])
        self.assertEqual([call.args[0].report for call in run.call_args_list], list(REPORTS))

    @patch("ecommerce_oltp_system.reporting.run")
    def test_explicit_target_runs_only_that_report(self, run):
        """Targeted execution retains the existing per-report filter options."""
        report_main(["daily", "--products", "1,2"])
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0].report.name, "daily")
        self.assertEqual(run.call_args.args[0].products, [1, 2])

    @patch("ecommerce_oltp_system.reporting.run")
    def test_only_selects_a_subset_of_reports(self, run):
        """Multiple target names are exported once each, in catalog order."""
        report_main(["all", "--only", "daily", "monthly"])
        self.assertEqual([call.args[0].report.name for call in run.call_args_list], ["monthly", "daily"])

    @patch("ecommerce_oltp_system.reporting.run")
    def test_output_options_work_before_or_after_target(self, run):
        """Child-parser defaults must not erase options supplied before the target."""
        for arguments in (["--output-dir", "custom", "monthly"], ["monthly", "--output-dir", "custom"]):
            with self.subTest(arguments=arguments):
                report_main(arguments)
                self.assertEqual(run.call_args.args[0].output_dir, Path("custom"))

    def test_all_reports_use_null_filters_and_default_top_n(self):
        """All-report mode preserves each function's own filter/default contract."""
        with patch("ecommerce_oltp_system.reporting.run") as run:
            report_main([])
        for call in run.call_args_list:
            args = call.args[0]
            self.assertEqual(args.top, args.report.top_default)
            for name in args.report.filters:
                self.assertIsNone(getattr(args, name))

    def test_all_reports_continue_after_one_failure_and_exit_nonzero(self):
        """Keep successful exports while making an incomplete run explicit."""
        with patch("ecommerce_oltp_system.reporting.run", side_effect=[SystemExit("missing function"), None]) as run:
            with redirect_stderr(io.StringIO()), self.assertRaisesRegex(SystemExit, "Saved 1/2 reports"):
                report_main(["all", "--only", "monthly", "daily"])
        self.assertEqual(run.call_count, 2)

    @patch("ecommerce_oltp_system.reporting.database_config", return_value={})
    @patch("ecommerce_oltp_system.reporting.execute_report")
    def test_report_saves_csv_without_printing_result_values(self, execute, _config):
        """CSV preserves headers, Unicode, quoted fields, dates, and exact decimals."""
        execute.return_value = (("month", "label", "total"), [(date(2025, 3, 1), 'Café, "one"', Decimal("12.30"))])
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            with patch("ecommerce_oltp_system.reporting.psycopg2.connect", return_value=MagicMock()), redirect_stdout(output):
                report_main(["monthly", "--output-dir", directory])
            paths = list(Path(directory).glob("*.csv"))
            self.assertEqual(len(paths), 1)
            with paths[0].open(encoding="utf-8", newline="") as source:
                self.assertEqual(list(csv.reader(source)), [["month", "label", "total"], ["2025-03-01", 'Café, "one"', "12.30"]])
            self.assertIn(str(paths[0]), output.getvalue())
        self.assertNotIn("Café", output.getvalue())

    @patch("ecommerce_oltp_system.reporting.database_config", return_value={})
    @patch("ecommerce_oltp_system.reporting.execute_report", return_value=(("month", "total"), []))
    def test_empty_result_saves_header_only_csv(self, _execute, _config):
        """A valid report with no rows is still a useful exported schema."""
        with tempfile.TemporaryDirectory() as directory:
            with patch("ecommerce_oltp_system.reporting.psycopg2.connect", return_value=MagicMock()), redirect_stdout(io.StringIO()):
                report_main(["monthly", "--output-dir", directory])
            with next(Path(directory).glob("*.csv")).open(newline="") as source:
                self.assertEqual(list(csv.reader(source)), [["month", "total"]])

    @patch("ecommerce_oltp_system.reporting.database_config", return_value={})
    @patch("ecommerce_oltp_system.reporting.execute_report", return_value=(("value",), [(1,), (2,), (3,)]))
    def test_export_limit_excludes_the_extra_truncation_row(self, _execute, _config):
        """The extra fetched row detects truncation but must not enter the CSV."""
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            with patch("ecommerce_oltp_system.reporting.psycopg2.connect", return_value=MagicMock()), redirect_stdout(output):
                report_main(["monthly", "--output-dir", directory, "--limit", "2"])
            with next(Path(directory).glob("*.csv")).open(newline="") as source:
                self.assertEqual(list(csv.reader(source)), [["value"], ["1"], ["2"]])
        self.assertIn("Limited to 2 rows", output.getvalue())

    @patch("ecommerce_oltp_system.reporting.database_config", return_value={})
    @patch("ecommerce_oltp_system.reporting.execute_report", return_value=(("value",), [(1,)]))
    def test_repeated_exports_do_not_overwrite_previous_csv(self, _execute, _config):
        """Each successful invocation creates a uniquely named result file."""
        with tempfile.TemporaryDirectory() as directory:
            with patch("ecommerce_oltp_system.reporting.psycopg2.connect", return_value=MagicMock()), redirect_stdout(io.StringIO()):
                for _ in range(2):
                    report_main(["monthly", "--output-dir", directory])
            self.assertEqual(len(list(Path(directory).glob("*.csv"))), 2)

    @patch("ecommerce_oltp_system.reporting.database_config", return_value={})
    @patch("ecommerce_oltp_system.reporting.execute_report", side_effect=psycopg2.errors.UndefinedFunction("missing"))
    def test_failed_query_creates_no_csv(self, _execute, _config):
        """Query failure must not leave an empty or apparently completed export."""
        with tempfile.TemporaryDirectory() as directory:
            with patch("ecommerce_oltp_system.reporting.psycopg2.connect", return_value=MagicMock()), self.assertRaises(SystemExit):
                report_main(["monthly", "--output-dir", directory])
            self.assertEqual(list(Path(directory).iterdir()), [])

    @patch("ecommerce_oltp_system.reporting.database_config", return_value={})
    @patch("ecommerce_oltp_system.reporting.execute_report", return_value=(("value",), [(1,)]))
    def test_failed_csv_write_removes_its_partial_file(self, _execute, _config):
        """Disk errors leave no final CSV that could be mistaken for success."""
        with tempfile.TemporaryDirectory() as directory:
            writer = MagicMock()
            writer.writerows.side_effect = OSError("disk full")
            with patch("ecommerce_oltp_system.reporting.psycopg2.connect", return_value=MagicMock()), patch("ecommerce_oltp_system.reporting.csv.writer", return_value=writer):
                with self.assertRaisesRegex(SystemExit, "disk full"):
                    report_main(["monthly", "--output-dir", directory])
            self.assertEqual(list(Path(directory).iterdir()), [])

    @patch("ecommerce_oltp_system.reporting.database_config", return_value={})
    @patch("ecommerce_oltp_system.reporting.execute_report", side_effect=psycopg2.errors.UndefinedFunction("missing"))
    def test_missing_function_explains_manual_deployment(self, _execute, _config):
        """Never install SQL automatically as a side effect of reporting."""
        database = MagicMock()
        with patch("ecommerce_oltp_system.reporting.psycopg2.connect", return_value=database):
            with self.assertRaisesRegex(SystemExit, "Deploy database/reporting/functions.sql"):
                main(["report", "monthly"])
        database.close.assert_called_once()

    @patch("ecommerce_oltp_system.generate.print_summary")
    @patch("ecommerce_oltp_system.generate.generate_order_files")
    def test_orders_only_reuses_existing_generator(self, generate, _summary):
        """Replace the old launcher without duplicating streaming generation."""
        main(["generate", "--orders-only", "--data-dir", "reference", "--orders", "12", "--orders-per-file", "5", "--seed", "7"])
        generate.assert_called_once_with(data_dir=Path("reference"), output_dir=None, order_count=12, orders_per_file=5, seed=7)

    def test_generation_modes_are_mutually_exclusive(self):
        """Reference-only and orders-only cannot be requested together."""
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["generate", "--base-only", "--orders-only"])
