"""Check that consolidation retains the historical benchmark inputs exactly."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from importlib.resources import files
from pathlib import Path

from scripts.reporting_workloads import CASES, ROOT, load_query_versions, read_measurements, read_sql_blocks, validate_output_directory


class ReportingArtifactTests(unittest.TestCase):
    """Guard benchmark reproducibility without running a performance workload."""

    def test_analytical_archive_matches_measured_sql_hashes(self):
        """All original/rewritten SQL hashes retain their historical meanings."""
        recorded = json.loads(Path("reports/sql_optimization/validation.json").read_text())
        for name, (original, optimized) in load_query_versions().items():
            with self.subTest(query=name):
                expected = recorded["query_versions"][name]
                self.assertEqual(hashlib.sha256(original.encode()).hexdigest(), expected["original_sha256"])
                self.assertEqual(hashlib.sha256(optimized.encode()).hexdigest(), expected["optimized_sha256"])

    def test_dynamic_candidate_archive_matches_measured_sql_hash(self):
        """The historic candidate remains independent of the canonical functions."""
        recorded = json.loads(Path("reports/dynamic_reports/validation.json").read_text())
        archived = Path("benchmarks/dynamic_optimized_20261013.sql").read_bytes()
        self.assertEqual(hashlib.sha256(archived).hexdigest(), recorded["optimized_function_sql_sha256"])

    def test_dynamic_benchmark_requires_explicit_overwrite(self):
        """An accidental rerun cannot erase a completed dynamic benchmark."""
        self._assert_overwrite_guard("scripts/benchmark_dynamic_reports.py")

    def test_analytical_benchmark_requires_explicit_overwrite(self):
        """An accidental rerun cannot erase a completed analytical benchmark."""
        self._assert_overwrite_guard("scripts/benchmark_sql_optimization.py")

    def _assert_overwrite_guard(self, script):
        """Refuse frozen historical output before any database access or file deletion."""
        profile = "dynamic" if "dynamic" in script else "analytical"
        directory = ROOT / CASES[profile]["historical_report"]
        summary = directory / "summary.csv"
        before = summary.read_bytes()
        outcome = subprocess.run(
            [sys.executable, script, "--run", "--output", str(directory)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(outcome.returncode, 2, outcome.stderr)
        self.assertIn("Historical results already exist", outcome.stderr)
        self.assertEqual(summary.read_bytes(), before)

    def test_generated_output_directory_is_reusable(self):
        """Repeated runs can replace nonhistorical output without accumulating folders."""
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "summary.csv").write_text("previous generated result")
            validate_output_directory(Path(directory))

    def test_cleanup_preserved_retained_artifact_bytes(self):
        """Retained SQL, measurements, metadata and representative plans match pre-move hashes."""
        recorded = json.loads((ROOT / "docs/cleanup_provenance.json").read_text())
        for artifact in recorded["files"]:
            with self.subTest(path=artifact["current"]):
                actual = hashlib.sha256((ROOT / artifact["current"]).read_bytes()).hexdigest()
                self.assertEqual(actual, artifact["sha256"])

    def test_schema_entrypoint_matches_installed_package_resource(self):
        """The root SQL path and packaged loader use one identical schema definition."""
        packaged = files("ecommerce_oltp_system.loader.sql").joinpath("schema.sql").read_bytes()
        self.assertEqual((ROOT / CASES["schema"]).read_bytes(), packaged)

    def test_examples_cover_all_thirteen_requirements(self):
        """The merged example file retains eight analytical and five dynamic cases."""
        examples = read_sql_blocks(ROOT / CASES["examples"])
        analytical = {case["id"] for case in CASES["analytical"]["cases"]}
        dynamic = {"monthly_revenue", "daily_revenue", "seller_performance", "top_products_per_brand", "order_status_summary"}
        self.assertEqual(set(examples), analytical | dynamic)

    def test_representative_plan_selection_matches_published_files(self):
        """Generated plan selection stays aligned with the compact historical layout."""
        for profile in ("analytical", "dynamic"):
            expected = {f"{plan['query']}_{plan['stage']}.txt" for plan in CASES[profile]["representative_plans"]}
            actual = {path.name for path in (ROOT / CASES[profile]["historical_report"] / "plans").glob("*.txt")}
            with self.subTest(profile=profile):
                self.assertEqual(actual, expected)

    def test_fixed_dynamic_calls_match_recorded_scenario(self):
        """Fixed date/filter parameters reproduce the previously measured function calls."""
        from scripts.benchmark_dynamic_reports import configured_report_calls

        recorded = json.loads((ROOT / "reports/dynamic_reports/validation.json").read_text())
        calls, filters = configured_report_calls()
        self.assertEqual(calls, recorded["report_calls"])
        self.assertEqual(filters, recorded["filters"])

    def test_padded_measurement_csv_retains_metrics_and_json_cells(self):
        """Visual CSV padding must not erase named metrics during regeneration."""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "measurements.csv"
            source.write_text(
                'stage    , query  , execution_ms , indexes\n'
                'original_no_index , q1 , 12.5 , "[""one"", ""two""]"\n'
            )
            result = read_measurements(source)
            self.assertEqual(result[0]["stage"], "original_no_index")
            self.assertEqual(result[0]["execution_ms"], "12.5")
            self.assertEqual(json.loads(result[0]["indexes"]), ["one", "two"])
