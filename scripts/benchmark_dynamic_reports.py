"""Compare the previous and optimized SQL report functions, with/without indexes.

The benchmark runs only against a disposable PostgreSQL clone. One warm-up and
five measured EXPLAIN ANALYZE calls are captured per report and index state.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import statistics
from pathlib import Path

import psycopg2

if __package__:
    from . import benchmark_sql_optimization as shared
    from .reporting_workloads import CASES, ROOT, read_measurements, validate_output_directory
else:
    import benchmark_sql_optimization as shared
    from reporting_workloads import CASES, ROOT, read_measurements, validate_output_directory


REPORT = ROOT / CASES["dynamic"]["output"]
RAW = REPORT / "raw"
PLANS = REPORT / "plans"
CLONE = "ecommerce_oltp_dynamic_reports_bench"
CANDIDATE_SQL = ROOT / CASES["functions"]
ORIGINAL_SQL = ROOT / CASES["dynamic"]["original_sql"]
START_DATE = CASES["dynamic"]["start_date"]
END_DATE = CASES["dynamic"]["end_date"]
STAGES = (
    ("old_no_indexes", "Old SQL / no workload indexes"),
    ("new_no_indexes", "Optimized SQL / no workload indexes"),
    ("new_with_indexes", "Optimized SQL / four workload indexes"),
)
EXPECTED_COLUMNS = {
    "monthly_revenue": ["month", "total_orders", "total_quantity", "total_revenue"],
    "daily_revenue": ["date", "total_orders", "total_quantity", "total_revenue"],
    "seller_performance": ["seller_id", "seller_name", "total_orders", "total_quantity", "total_revenue"],
    "top_products_per_brand": ["brand_id", "brand_name", "product_id", "product_name", "total_quantity", "total_revenue"],
    "order_status_summary": ["status", "total_orders", "total_revenue"],
}


def _array(ids: list[int]) -> str:
    """Format database-selected integer filters as a typed SQL array literal."""
    return "ARRAY[" + ", ".join(str(value) for value in ids) + "]::INTEGER[]"


def configured_report_calls() -> tuple[dict[str, str], dict[str, list[int]]]:
    """Use the fixed date/filter scenario recorded in benchmarks/cases.json.

    These IDs reproduce the previously measured dataset. Contract validation
    rejects empty report results rather than silently changing the workload.
    """
    filters = CASES["dynamic"]["filters"]
    top_n = CASES["dynamic"]["top_n"]
    start, end = f"DATE '{START_DATE}'", f"DATE '{END_DATE}'"
    calls = {
        "monthly_revenue": f"SELECT * FROM report_monthly_revenue({start}, {end})",
        "daily_revenue": f"SELECT * FROM report_daily_revenue({start}, {end}, {_array(filters['product_ids'])})",
        "seller_performance": f"SELECT * FROM report_seller_performance({start}, {end}, {_array(filters['category_ids'])}, {_array(filters['brand_ids'])})",
        "top_products_per_brand": f"SELECT * FROM report_top_products_per_brand({start}, {end}, {_array(filters['seller_ids'])}, {top_n})",
        "order_status_summary": f"SELECT * FROM report_order_status_summary({start}, {end}, {_array(filters['seller_ids'])}, {_array(filters['category_ids'])})",
    }
    return calls, filters


def reset_outputs() -> None:
    """Overwrite only generated report output; leave the function SQL untouched."""
    import shutil

    REPORT.mkdir(parents=True, exist_ok=True)
    for path in (RAW, PLANS):
        if path.exists():
            shutil.rmtree(path)
    for name in ("README.md", "summary.csv", "measurements.csv", "environment.json", "validation.json"):
        target = REPORT / name
        if target.exists():
            target.unlink()


def install_and_validate_functions(database, calls: dict[str, str]) -> dict:
    """Install reports on the clone and verify each return-column contract."""
    with database.cursor() as cursor:
        cursor.execute(CANDIDATE_SQL.read_text(encoding="utf-8"))
        database.commit()
    return validate_function_contracts(database, calls)


def validate_function_contracts(database, calls: dict[str, str]) -> dict:
    """Check function output columns and row counts without replacing definitions."""
    contracts = {}
    with database.cursor() as cursor:
        for name, call in calls.items():
            cursor.execute(f"SELECT * FROM ({call}) AS report_result LIMIT 0")
            columns = [column.name for column in cursor.description]
            if columns != EXPECTED_COLUMNS[name]:
                raise RuntimeError(f"{name} column contract mismatch: {columns}")
            cursor.execute(f"SELECT count(*) FROM ({call}) AS report_result")
            result_rows = cursor.fetchone()[0]
            if not result_rows:
                raise RuntimeError(f"{name}: fixed benchmark filters returned no rows; check the dataset/cases.json")
            contracts[name] = {"columns": columns, "result_rows": result_rows}
    database.commit()
    return contracts


def capture_installed_function_sql(database) -> str:
    """Save the clone's existing report functions as the pre-optimization baseline."""
    names = [f"report_{name}" for name in EXPECTED_COLUMNS]
    with database.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.proname, pg_get_functiondef(p.oid)
            FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = current_schema() AND p.proname = ANY(%s)
            ORDER BY p.proname, p.oid
            """,
            (names,),
        )
        definitions = cursor.fetchall()
    if len(definitions) != len(names):
        found = [name for name, _definition in definitions]
        raise RuntimeError(
            f"Expected the five pre-existing report functions on the source clone; found {found}"
        )
    return "\n\n".join(definition for _name, definition in definitions) + "\n"


def validate_result_equivalence(database, calls: dict[str, str], filters: dict[str, list[int]]) -> dict[str, int]:
    """Compare every report's result bag against an independently written query."""
    start, end = f"DATE '{START_DATE}'", f"DATE '{END_DATE}'"
    products, sellers = _array(filters["product_ids"]), _array(filters["seller_ids"])
    categories, brands = _array(filters["category_ids"]), _array(filters["brand_ids"])
    top_n = CASES["dynamic"]["top_n"]
    references = {
        "monthly_revenue": f"""SELECT date_trunc('month', o.order_date)::date, count(DISTINCT o.order_id), sum(oi.quantity)::bigint, sum(oi.subtotal)
            FROM \"order\" o JOIN order_item oi ON oi.order_id=o.order_id
            WHERE o.order_date >= {start} AND o.order_date < {end} AND NOT o.is_deleted AND NOT oi.is_deleted
            GROUP BY 1 ORDER BY 1""",
        "daily_revenue": f"""SELECT o.order_date::date, count(DISTINCT o.order_id), sum(oi.quantity)::bigint, sum(oi.subtotal)
            FROM \"order\" o JOIN order_item oi ON oi.order_id=o.order_id
            WHERE o.order_date >= {start} AND o.order_date < {end} AND oi.product_id=ANY({products})
              AND NOT o.is_deleted AND NOT oi.is_deleted GROUP BY 1 ORDER BY 1""",
        "seller_performance": f"""SELECT s.seller_id, s.seller_name, count(DISTINCT o.order_id), sum(oi.quantity)::bigint, sum(oi.subtotal)
            FROM order_item oi JOIN \"order\" o ON o.order_id=oi.order_id
            JOIN product p ON p.product_id=oi.product_id JOIN seller s ON s.seller_id=p.seller_id
            WHERE o.order_date >= {start} AND o.order_date < {end} AND p.category_id=ANY({categories}) AND p.brand_id=ANY({brands})
              AND NOT o.is_deleted AND NOT oi.is_deleted AND NOT p.is_deleted AND NOT s.is_deleted
            GROUP BY s.seller_id,s.seller_name ORDER BY s.seller_id""",
        "top_products_per_brand": f"""WITH sales AS (
            SELECT b.brand_id,b.brand_name,p.product_id,p.product_name,sum(oi.quantity)::bigint AS total_quantity,sum(oi.subtotal) AS total_revenue
            FROM order_item oi JOIN \"order\" o ON o.order_id=oi.order_id JOIN product p ON p.product_id=oi.product_id
            JOIN brand b ON b.brand_id=p.brand_id
            WHERE o.order_date >= {start} AND o.order_date < {end} AND p.seller_id=ANY({sellers})
              AND NOT o.is_deleted AND NOT oi.is_deleted AND NOT p.is_deleted AND NOT b.is_deleted
            GROUP BY b.brand_id,b.brand_name,p.product_id,p.product_name
        ), ranked AS (
            SELECT *,row_number() OVER (PARTITION BY brand_id ORDER BY total_quantity DESC,total_revenue DESC,product_id) AS rn
            FROM sales
        ) SELECT brand_id,brand_name,product_id,product_name,total_quantity,total_revenue FROM ranked WHERE rn <= {top_n} ORDER BY brand_id,rn""",
        "order_status_summary": f"""SELECT o.status,count(*),sum(o.total_amount)
            FROM \"order\" o WHERE o.order_date >= {start} AND o.order_date < {end} AND NOT o.is_deleted
              AND EXISTS (SELECT 1 FROM order_item oi JOIN product p ON p.product_id=oi.product_id
                WHERE oi.order_id=o.order_id AND NOT oi.is_deleted AND NOT p.is_deleted
                  AND p.seller_id=ANY({sellers}) AND p.category_id=ANY({categories}))
            GROUP BY o.status ORDER BY o.status""",
    }
    differing_rows = {}
    with database.cursor() as cursor:
        for name, reference in references.items():
            actual = calls[name]
            cursor.execute(f"""
                WITH actual_rows AS ({actual}), expected_rows AS ({reference}), differences AS (
                    (SELECT * FROM actual_rows EXCEPT ALL SELECT * FROM expected_rows)
                    UNION ALL
                    (SELECT * FROM expected_rows EXCEPT ALL SELECT * FROM actual_rows)
                ) SELECT count(*) FROM differences
            """)
            differing_rows[name] = cursor.fetchone()[0]
    database.commit()
    if any(differing_rows.values()):
        raise RuntimeError(f"Dynamic report result mismatch: {differing_rows}")
    return differing_rows


def capture_stage(database, stage: str, calls: dict[str, str], runs: int = CASES["dynamic"]["measured_runs"]) -> list[dict]:
    """Capture randomized report plans and server timings for one index state."""
    database.autocommit = False
    database.set_session(readonly=True, isolation_level="REPEATABLE READ")
    records, samples, plans = [], {name: [] for name in calls}, {}
    for run in range(runs + 1):
        report_names = list(calls)
        random.Random(CASES["dynamic"]["shuffle_seed"] + run).shuffle(report_names)
        for name in report_names:
            with database.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = '15min'")
                cursor.execute("EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS, FORMAT JSON) " + calls[name])
                explain = cursor.fetchone()[0][0]
            plans[(name, run)] = explain
            directory = RAW / stage
            directory.mkdir(parents=True, exist_ok=True)
            (directory / f"{name}.run_{run:02d}.plan.json").write_text(
                json.dumps(explain, separators=(",", ":")) + "\n", encoding="utf-8"
            )
            metrics = shared.plan_metrics(explain)
            if run:
                samples[name].append(metrics["execution_ms"])
                records.append({"stage": stage, "query": name, "run": run, **metrics})
            print(f"{stage} {'warmup' if not run else 'run '+str(run)} {name}: {metrics['execution_ms']:.3f} ms", flush=True)
    database.rollback()
    # Restore a writable default before the next stage installs/replaces functions.
    database.set_session(readonly=False, isolation_level="READ COMMITTED")

    stage_summary = []
    for name, times in samples.items():
        median = statistics.median(times)
        representative = min(range(1, runs + 1), key=lambda number: abs(times[number - 1] - median))
        plan = plans[(name, representative)]
        stage_summary.append({
            "query": name, "measured_runs": runs, "median_ms": median,
            "min_ms": min(times), "max_ms": max(times),
            "stdev_ms": statistics.stdev(times) if runs > 1 else 0,
            "coefficient_of_variation": statistics.stdev(times) / median if median else 0,
            "rows": plan["Plan"].get("Actual Rows", 0),
            "indexes": shared.plan_metrics(plan)["indexes"],
            "representative_run": representative,
        })
    (RAW / f"{stage}.summary.json").write_text(json.dumps(stage_summary, indent=2) + "\n")
    return records


def write_csv(path: Path, rows: list[dict], columns: tuple[str, ...]) -> None:
    """Serialize benchmark rows with nested plan metrics as compact JSON cells."""
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(row[key], sort_keys=True) if isinstance(row.get(key), (dict, list)) else row.get(key) for key in columns})


def write_report(records: list[dict], contracts: dict, environments: dict, calls: dict[str, str], filters: dict[str, list[int]], equivalence: dict[str, dict[str, int]], old_sql: str, candidate_hash: str | None = None, assumptions: dict | None = None) -> None:
    """Write timings, selected plans, and concise conclusions from saved captures."""
    summaries = {
        stage: {row["query"]: row for row in json.loads((RAW / f"{stage}.summary.json").read_text())}
        for stage, _label in STAGES
    }
    summary_rows = []
    for name in calls:
        old = summaries["old_no_indexes"][name]
        optimized = summaries["new_no_indexes"][name]
        for stage, _label in STAGES:
            current = summaries[stage][name]
            summary_rows.append({
                "stage": stage, **current,
                "speedup_vs_old": old["median_ms"] / current["median_ms"],
                "speedup_vs_optimized_no_indexes": optimized["median_ms"] / current["median_ms"],
            })
    summary_columns = ("stage", "query", "measured_runs", "median_ms", "min_ms", "max_ms", "stdev_ms", "coefficient_of_variation", "rows", "indexes", "speedup_vs_old", "speedup_vs_optimized_no_indexes")
    write_csv(REPORT / "summary.csv", summary_rows, summary_columns)
    write_csv(REPORT / "measurements.csv", records, (
        "stage", "query", "run", "execution_ms", "planning_ms", "shared_hit_blocks",
        "shared_read_blocks", "temp_read_blocks", "temp_written_blocks", "actual_rows",
        "estimated_rows", "indexes", "scan_types", "join_types", "aggregate_types", "sorts", "hashes",
    ))

    validation = {
        "old_function_sql_sha256": hashlib.sha256(old_sql.encode("utf-8")).hexdigest(),
        "optimized_function_sql_sha256": candidate_hash or hashlib.sha256(CANDIDATE_SQL.read_bytes()).hexdigest(),
        "date_window": {"start_inclusive": START_DATE, "end_exclusive": END_DATE},
        "contracts_by_version": contracts,
        "filters": filters,
        "result_equivalence_differing_rows": equivalence,
        "report_calls": calls,
        "candidate_sql": str(CANDIDATE_SQL),
    }
    if assumptions is not None:
        validation["assumptions"] = assumptions
    (REPORT / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    (REPORT / "environment.json").write_text(json.dumps({
        "captured_at": environments["new_with_indexes"]["captured_at"],
        "benchmark_database": CLONE,
        "stages": {stage: {"label": label, "performance_indexes": list(shared.INDEX_NAMES) if stage == "new_with_indexes" else []}
                   for stage, label in STAGES},
        "database": environments["new_with_indexes"],
        "method": {"warmup_runs": 1, "measured_runs": 5, "cache": "warm; not flushed",
                   "plan": "EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS, FORMAT JSON)",
                   "comparison": "old SQL -> optimized SQL without workload indexes -> optimized SQL with workload indexes"},
    }, indent=2) + "\n")

    if PLANS.exists():
        import shutil
        shutil.rmtree(PLANS)
    PLANS.mkdir(parents=True, exist_ok=True)
    selected = {(plan["stage"], plan["query"]) for plan in CASES["dynamic"]["representative_plans"]}
    for stage, _label in STAGES:
        for name in calls:
            if (stage, name) not in selected:
                continue
            summary = summaries[stage][name]
            source = RAW / stage / f"{name}.run_{summary['representative_run']:02d}.plan.json"
            target = PLANS / f"{name}_{stage}.txt"
            target.write_text(shared.render_compact_plan(json.loads(source.read_text())) + "\n", encoding="utf-8")

    lines = [
        "# Dynamic SQL reports: performance review", "",
        f"Benchmark database: `{CLONE}`. Dataset: {environments['new_with_indexes']['row_counts'][0]:,} orders and {environments['new_with_indexes']['row_counts'][1]:,} order items. The source database was not modified.", "",
        "## Method", "",
        "The baseline definitions come from `benchmarks/dynamic_original.sql`; candidate definitions are selected with `--candidate-sql` (canonical reporting functions by default). Both versions ran with one warm-up and five measured `EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS, FORMAT JSON)` executions without workload indexes. The optimized version was then measured again with four workload indexes. Primary/unique indexes and constraints remained intact. Each stage used the same data and parameters with randomized report order; caches were warm and not flushed; tables were analyzed before each stage. This separates the SQL rewrite from the additional index effect.", "",
        "## Results", "",
        "Execution times are PostgreSQL server medians. `Old → optimized` compares the versions without workload indexes; `optimized → indexed` isolates the index addition. Run-level timings and buffer/temp metrics are in [measurements.csv](measurements.csv); summary statistics are in [summary.csv](summary.csv).", "",
        "| Report | Old SQL | Optimized SQL | Optimized + indexes | Old → optimized | Optimized → indexed | Plan notes |", "|---|---:|---:|---:|---:|---:|---|",
    ]
    for name in calls:
        old = summaries["old_no_indexes"][name]
        new = summaries["new_no_indexes"][name]
        indexed = summaries["new_with_indexes"][name]
        used_indexes = [index for index in indexed["indexes"] if index in shared.INDEX_NAMES]
        used = ", ".join(used_indexes) or "no workload index used"
        if not used_indexes and new["min_ms"] <= indexed["max_ms"] and indexed["min_ms"] <= new["max_ms"]:
            used += "; ranges overlap, treat median difference as noise"
        lines.append(f"| `{name}` | {old['median_ms']:.3f} ms | {new['median_ms']:.3f} ms | {indexed['median_ms']:.3f} ms | {old['median_ms']/new['median_ms']:.2f}× | {new['median_ms']/indexed['median_ms']:.2f}× | {used} |")
    lines += ["", "## Function contracts", "", "Both SQL versions were checked against independent reference queries using bidirectional `EXCEPT ALL`; every report returned zero differing rows in each version. All reports use a start-inclusive, end-exclusive date window. `NULL` optional ID arrays mean no filter; empty arrays match no rows. Product/category/brand/seller filters apply to matching line items. Revenue in product-scoped reports is item subtotal, while the status report uses order total amount and counts each order once.", "", "| Function | Return columns |", "|---|---|", "| `report_monthly_revenue` | month, total_orders, total_quantity, total_revenue |", "| `report_daily_revenue` | date, total_orders, total_quantity, total_revenue |", "| `report_seller_performance` | seller_id, seller_name, total_orders, total_quantity, total_revenue |", "| `report_top_products_per_brand` | brand_id, brand_name, product_id, product_name, total_quantity, total_revenue |", "| `report_order_status_summary` | status, total_orders, total_revenue |", "", "Soft-deleted orders and line items are excluded; product/seller/brand rows are excluded where they affect attribution. The top-products function returns the top N products per brand, ranked by quantity, then revenue, then product ID. Status output includes all statuses present in the schema.", "", "## Index and plan interpretation", "", "The indexed stage shows the combined impact of four workload indexes; it does not isolate each index's contribution. Category/brand filter fields are not independently indexed by this benchmark, and no partitions were added. Broad date-window aggregates may remain scan- and aggregation-bound.", "", "Selected median-nearest plans illustrating important rewrites, index benefits, and remaining bottlenecks are in [plans/](plans/). Full plans and the captured old SQL definition are in gitignored [raw/](raw/). Query contracts and tested parameters are in [validation.json](validation.json); PostgreSQL settings and row counts are in [environment.json](environment.json).", "", "## Reproduce", "", "From the repository root, after configuring `database.ini` and starting the PostgreSQL container:", "", "```bash", ".venv/bin/python scripts/benchmark_dynamic_reports.py --prepare", ".venv/bin/python scripts/benchmark_dynamic_reports.py --run", ".venv/bin/python scripts/benchmark_dynamic_reports.py --report-only", ".venv/bin/python scripts/benchmark_dynamic_reports.py --cleanup", "```", "", "The runner reuses the configured latest/ output; frozen historical reports require explicit `--overwrite`. Use `--candidate-sql` to select canonical or archived SQL. Existing clones are not overwritten and functions are replaced only in the clone.", ""]
    (REPORT / "README.md").write_text("\n".join(lines), encoding="utf-8")


def run_benchmark() -> None:
    """Measure the old SQL, optimized SQL, and optimized SQL with indexes."""
    reset_outputs()
    database = psycopg2.connect(**shared.connection_settings(CLONE))
    try:
        # Archived order-date and current item-date reports are comparable only
        # while the generated data's denormalized timestamps agree.
        assumptions = shared.verify_data_assumptions(database)
        # Use the archived baseline so changing deployed functions cannot change stage A.
        with database.cursor() as cursor:
            cursor.execute(ORIGINAL_SQL.read_text(encoding="utf-8"))
        database.commit()
        old_sql = capture_installed_function_sql(database)
        RAW.mkdir(parents=True, exist_ok=True)
        (RAW / "old_dynamic_reports.sql").write_text(old_sql, encoding="utf-8")
        calls, filters = configured_report_calls()

        versions = {"old": {"contracts": validate_function_contracts(database, calls)}}
        versions["old"]["equivalence"] = validate_result_equivalence(database, calls, filters)

        result_rows, environments = [], {}
        stage_versions = (
            ("old_no_indexes", "old"),
            ("new_no_indexes", "optimized"),
            ("new_with_indexes", "optimized"),
        )
        for stage, version in stage_versions:
            if version == "optimized" and version not in versions:
                # Replace only the clone's old report functions with the candidate SQL.
                versions[version] = {
                    "contracts": install_and_validate_functions(database, calls)
                }
                versions[version]["equivalence"] = validate_result_equivalence(database, calls, filters)
            shared.set_index_state(database, stage == "new_with_indexes")
            with database.cursor() as cursor:
                cursor.execute('ANALYZE "order"')
                cursor.execute("ANALYZE order_item")
                cursor.execute("ANALYZE product")
            database.commit()
            metadata = shared.capture_metadata(database, RAW / f"{stage}.environment.json")
            present = {row[1] for row in metadata["indexes"]}
            existing = present.intersection(shared.INDEX_NAMES)
            expected = set(shared.INDEX_NAMES) if stage == "new_with_indexes" else set()
            if existing != expected:
                raise RuntimeError(f"Unexpected workload-index state for {stage}: {sorted(existing)}")
            environments[stage] = metadata
            result_rows.extend(capture_stage(database, stage, calls))
        contracts = {version: values["contracts"] for version, values in versions.items()}
        equivalence = {version: values["equivalence"] for version, values in versions.items()}
        write_report(result_rows, contracts, environments, calls, filters, equivalence, old_sql, assumptions=assumptions)
    finally:
        database.close()


def main() -> None:
    """Prepare, run, or remove the dedicated disposable report benchmark clone."""
    global REPORT, RAW, PLANS, CANDIDATE_SQL
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPORT, help="Stable generated-results directory; repeated runs replace its output.")
    parser.add_argument("--candidate-sql", type=Path, default=CANDIDATE_SQL, help="Canonical functions or an archived candidate for historical reproduction.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing protected historical evidence explicitly.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true", help="Clone ecommerce_oltp into an isolated benchmark database.")
    action.add_argument("--run", action="store_true", help="Install functions and benchmark each with indexes off/on.")
    action.add_argument("--cleanup", action="store_true", help="Drop only the dynamic-report benchmark clone.")
    action.add_argument("--report-only", action="store_true", help="Rebuild report artifacts from saved benchmark captures.")
    args = parser.parse_args()
    REPORT, CANDIDATE_SQL = args.output, args.candidate_sql
    RAW, PLANS = REPORT / "raw", REPORT / "plans"
    if args.run or args.report_only:
        try:
            validate_output_directory(REPORT, args.overwrite)
        except ValueError as error:
            parser.error(str(error))
    if args.prepare:
        shared.prepare_clone(CLONE)
    elif args.cleanup:
        shared.cleanup_clone(CLONE)
    elif args.report_only:
        validation = json.loads((REPORT / "validation.json").read_text())
        CANDIDATE_SQL = Path(validation.get("candidate_sql", "benchmarks/dynamic_optimized_20261013.sql"))
        environments = {
            stage: json.loads((RAW / f"{stage}.environment.json").read_text())
            for stage, _label in STAGES
        }
        records = read_measurements(REPORT / "measurements.csv")
        old_sql = (RAW / "old_dynamic_reports.sql").read_text(encoding="utf-8")
        write_report(records, validation["contracts_by_version"], environments, validation["report_calls"],
                     validation["filters"], validation["result_equivalence_differing_rows"], old_sql,
                     validation["optimized_function_sql_sha256"], validation.get("assumptions"))
    else:
        run_benchmark()


if __name__ == "__main__":
    main()
