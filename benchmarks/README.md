# Fixed SQL workloads and reproducibility

[cases.json](cases.json) is the shared configuration for case IDs, dates/filters,
measured-run counts, shuffle seeds, report locations, and selected plans.
JSON uses Python's standard library; no YAML dependency was added.

| Input | Purpose |
|---|---|
| [original_queries.sql](original_queries.sql) | Eight measured original analytical statements, in named blocks |
| [optimized_queries.sql](optimized_queries.sql) | Four actual rewrites; unchanged cases reuse their original statement |
| [dynamic_original.sql](dynamic_original.sql) | Five pre-rewrite functions captured from PostgreSQL |
| [dynamic_optimized_20261013.sql](dynamic_optimized_20261013.sql) | Exact historical candidate, including the top-brand regression |
| [Canonical functions](../database/reporting/functions.sql) | Current production reporting logic; distinct from historical benchmark code |
| [Approved indexes](../database/indexes.sql) | Single definition of the four benchmarked performance indexes |

Analytical SQL literals stay inside the archived statements: their per-case hashes
match historical validation. Dynamic filter IDs/date bounds are fixed to the
recorded dataset instead of changing the benchmark scenario on every run.
Empty report results fail clearly when the configured dataset is incompatible.

## Run manually

From the repository root with `database.ini`, the running PostgreSQL container,
Docker access and enough disk space for a clone:

```bash
.venv/bin/python scripts/benchmark_sql_optimization.py --prepare
.venv/bin/python scripts/benchmark_sql_optimization.py --run
.venv/bin/python scripts/benchmark_sql_optimization.py --write-test  # optional
.venv/bin/python scripts/benchmark_sql_optimization.py --cleanup

.venv/bin/python scripts/benchmark_dynamic_reports.py --prepare
.venv/bin/python scripts/benchmark_dynamic_reports.py --run
.venv/bin/python scripts/benchmark_dynamic_reports.py --cleanup
```

The analytical runner writes `reports/sql_optimization/latest/`; the dynamic
runner writes `reports/dynamic_reports/latest/`. Each directory has README,
summary/measurements CSVs, environment/validation JSON, selected TXT plans under
`plans/`, and full optional captures under ignored `raw/`. A repeat replaces
that same generated directory instead of accumulating timestamped runs.

The source database remains read-only; workload indexes are toggled only in a
disposable clone. One warm-up, five measured executions and the existing fixed
shuffle seeds preserve the three-stage methodology. These are expensive manual
experiments, not normal test-suite operations.

The archived reports at [sql_optimization/](../reports/sql_optimization/README.md)
and [dynamic_reports/](../reports/dynamic_reports/README.md) remain frozen. Writing
directly to those paths requires explicit `--overwrite`. Prefer generated
`latest/` directories. No historical measurements were regenerated during cleanup.

To reproduce the historical dynamic candidate rather than current functions:

```bash
# Prepare the dynamic clone first, then use the same stable output path:
.venv/bin/python scripts/benchmark_dynamic_reports.py --run \
  --candidate-sql benchmarks/dynamic_optimized_20261013.sql
```

The analytical runner always compares its archived originals/rewrites. The dynamic
runner defaults to current canonical functions; validation records the candidate
path/hash. Do not present historical candidate measurements as current-function
timings. Report-only regeneration reads saved raw captures and preserves recorded
candidate hashes; select the same `--output` if using a custom output directory.

Source auditing and single-run snapshots are separate:

```bash
.venv/bin/python scripts/verify_dataset.py
.venv/bin/python scripts/snapshot_queries.py
```

The verifier writes `reports/data_validation/latest/`; snapshots use canonical
function calls from `database/reporting/examples.sql` and write
`reports/sql_optimization/latest_snapshot/`. Both reuse their generated directory.
Install the functions before snapshotting. These are single executions, not
median benchmark runs.

Original single-run metadata remains under `reports/sql_optimization/baseline/`.
Full baseline plans/CSVs are preserved locally under ignored
`reports/sql_optimization/raw/baseline/`. Their absence on a fresh checkout does
not remove the committed summary/environment or controlled benchmark evidence.
