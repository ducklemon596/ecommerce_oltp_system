"""Protect the active SQL examples, packaged schema, and simple CLI contracts."""

import re
import tomllib
import unittest
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

from ecommerce_oltp_system.cli import main
from tests.reporting_support import (
    ROOT, function_definitions, standalone_queries,
)


class ReportingSqlTests(unittest.TestCase):
    """Catch drift without PostgreSQL or historical benchmark dependencies."""

    def test_every_function_has_a_standalone_query_in_catalog_order(self):
        definitions = function_definitions()
        self.assertEqual(len(definitions), 12)
        self.assertEqual(list(standalone_queries()), list(definitions))

    def test_standalone_queries_are_complete_literal_selects(self):
        """Literal-only examples omit function parameter guards; DB tests check values."""
        for name, query in standalone_queries().items():
            with self.subTest(function=name):
                self.assertRegex(query, r"^(SELECT|WITH)\b")
                self.assertTrue(query.endswith(";"))
                self.assertNotRegex(query, r"\bp_\w+\b|\breport_\w+\s*\(|\bARRAY\[|\bANY\(|infinity")

    def test_schema_entrypoint_matches_installed_package_resource(self):
        packaged = files("ecommerce_oltp_system.loader.sql").joinpath("schema.sql").read_bytes()
        self.assertEqual((ROOT / "database/schema.sql").read_bytes(), packaged)


class CliTests(unittest.TestCase):
    """Exercise argument forwarding without connecting or writing generated files."""

    def test_only_supported_entrypoints_are_registered(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())
        self.assertEqual(project["project"]["scripts"], {
            "ecommerce": "ecommerce_oltp_system.cli:main",
            "report": "ecommerce_oltp_system.reporting:main",
        })

    @patch("ecommerce_oltp_system.generate.run")
    def test_generate_preserves_dataset_options(self, run):
        main(["generate", "--orders", "12", "--orders-per-file", "5", "--seed", "7", "--output-dir", "sample"])
        args = run.call_args.args[0]
        self.assertEqual((args.orders, args.orders_per_file, args.seed, args.output_dir), (12, 5, 7, Path("sample")))

    @patch("ecommerce_oltp_system.loader.pipeline.run")
    def test_load_preserves_connection_and_file_options(self, run):
        main(["load", "--config", "test.ini", "--section", "test", "--data-dir", "sample", "--skip-schema"])
        args = run.call_args.args[0]
        self.assertEqual((args.config, args.section, args.data_dir, args.skip_schema), (Path("test.ini"), "test", Path("sample"), True))

    @patch("ecommerce_oltp_system.loader.pipeline.run")
    def test_init_db_delegates_schema_only(self, run):
        main(["init-db", "--config", "test.ini"])
        args = run.call_args.args[0]
        self.assertTrue(args.schema_only)
        self.assertFalse(args.skip_schema)
        self.assertEqual(args.config, Path("test.ini"))
