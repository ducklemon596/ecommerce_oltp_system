"""Nonbenchmark CLI walkthrough in one explicitly configured disposable schema."""

import configparser
import csv
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from psycopg2 import sql

from ecommerce_oltp_system.database_setup import RECOMMENDED_INDEXES
from ecommerce_oltp_system.reporting import GROUPS, REPORTS
from tests.integration_support import connect_test_database, test_settings
from tests.reporting_support import ROOT, function_definitions


class CliSmokeTests(unittest.TestCase):
    def test_generate_load_setup_export_and_resume(self):
        """Verify the public demo and resume with no dependency on primary data."""
        settings = test_settings(explicit=True)
        admin = connect_test_database(settings)
        self.addCleanup(admin.close)
        schema = f"cli_smoke_{uuid4().hex}"
        with admin:
            with admin.cursor() as cursor:
                cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

        def drop_created_schema():
            # Registered only after creation succeeds; cleanup errors fail the test.
            with admin:
                with admin.cursor() as cursor:
                    cursor.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))

        self.addCleanup(drop_created_schema)
        with tempfile.TemporaryDirectory(prefix="ecommerce-cli-smoke-") as directory:
            root = Path(directory)
            config = root / "test.ini"
            parser = configparser.ConfigParser(interpolation=None)
            parser["postgresql"] = {**settings, "options": f"-c search_path={schema}"}
            with config.open("w") as output:
                parser.write(output)
            config.chmod(0o600)

            def cli(*arguments):
                command = [str(Path(sys.executable).with_name("ecommerce")), *map(str, arguments)]
                result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=120)
                self.assertEqual(result.returncode, 0, f"CLI failed: {arguments}\n{result.stdout}\n{result.stderr}")
                return result.stdout

            data = root / "data"
            cli("generate", "--output-dir", data, "--orders", 40, "--orders-per-file", 20, "--seed", 42)
            load = ("load", "--config", config, "--data-dir", data, "--indexes", "recommended", "--sql-dir", ROOT / "database")
            cli(*load)
            database = connect_test_database({**settings, "options": f"-c search_path={schema}"})
            self.addCleanup(database.close)

            def counts():
                with database:
                    with database.cursor() as cursor:
                        return tuple(self._count(cursor, name) for name in ("order", "order_item", "load_checkpoint"))

            first_counts = counts()
            self.assertEqual(first_counts[0], 40)
            self.assertGreaterEqual(first_counts[1], 40)
            self.assertEqual(first_counts[2], 11)  # Seven references and two parent/child pairs.
            with database:
                with database.cursor() as cursor:
                    cursor.execute("SELECT c.relname, i.indisunique FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s", (schema,))
                    indexes = cursor.fetchall()
            self.assertEqual(sum(unique for _, unique in indexes), 25)
            self.assertEqual({name for name, unique in indexes if not unique}, set(RECOMMENDED_INDEXES))

            destination = root / "exports"
            definitions = function_definitions()
            by_name = {report.name: report for report in REPORTS}
            outputs = []
            for _ in range(2):
                for group in GROUPS:
                    outputs.append(cli("report", group, "--config", config, "--start", "2025-01-01", "--end", "2025-06-01", "--limit", 2, "--output-dir", destination))
            self.assertIn("Limited to 2 rows", "\n".join(outputs))
            paths = list(destination.glob("*/*.csv"))
            self.assertEqual(len(paths), 2 * sum(map(len, GROUPS.values())))
            self.assertEqual(len({path.name for path in paths}), len(paths))
            for path in paths:
                report_name = path.name.split("_", 1)[0]
                self.assertIn(report_name, GROUPS[path.parent.name])
                columns = re.findall(r"(?:^|,)\s*(\w+)\s+", definitions[by_name[report_name].function][1])
                with path.open(newline="", encoding="utf-8") as source:
                    rows = list(csv.reader(source))
                self.assertEqual(rows[0], columns)
                self.assertLessEqual(len(rows) - 1, 2)

            resumed = cli(*load)
            self.assertEqual(len(re.findall(r"^SKIPPED .* rows for", resumed, re.M)), 7)
            self.assertEqual(counts(), first_counts)
            print(f"CLI smoke verified: {first_counts[0]} orders, {first_counts[1]} items, {first_counts[2]} checkpoints; 25 mandatory + C1/C2 indexes; {len(paths)} bounded CSVs; repeat-load counts unchanged.")

    @staticmethod
    def _count(cursor, table):
        cursor.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table)))
        return cursor.fetchone()[0]
