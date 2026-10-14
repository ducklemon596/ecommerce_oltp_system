# Repository cleanup inventory

Audited before this migration on 2026-10-14. Existing generator/loader modules
are cohesive and remain in place. This is a filesystem/documentation cleanup:
no dataset regeneration, index changes, partition migration, or full benchmark.

| Existing files / family | Action | Destination / reason |
|---|---|---|
| `src/ecommerce_oltp_system/generators/**`, generation entry point | KEEP | Existing generation, streaming, and validation responsibilities remain intact. |
| `src/ecommerce_oltp_system/loader/**`, loading entry point | KEEP | Preserve installed-package schema resources, transaction, checkpoint, COPY and UPSERT behavior. |
| Packaged `loader/sql/schema.sql` | KEEP | Required by `importlib.resources` for installed loaders. Expose `database/schema.sql` as a link to this same file, avoiding duplicate DDL. |
| `database/reporting/report_functions.sql` | MOVE | `database/reporting/functions.sql`; retain the already validated 12 functions and five public signatures unchanged. |
| `reports/README.md` function catalog | MOVE | `database/reporting/README.md`; catalog belongs beside canonical functions. |
| `reports/queries/*.sql` | MERGE, DELETE | Named blocks in `database/reporting/examples.sql` preserve all eight calls. Remove the now redundant individual files. Add five existing dynamic examples. |
| `benchmarks/queries/analytical/*.sql` | MERGE, DELETE | `benchmarks/original_queries.sql` and `benchmarks/optimized_queries.sql`, keyed by original query IDs. Store only actual rewrites in the latter; unchanged cases reuse baseline SQL. Historical per-query hashes must stay equal. |
| `benchmarks/queries/dynamic_original.sql` | MOVE | `benchmarks/dynamic_original.sql`; exact measured baseline remains necessary. |
| `benchmarks/queries/dynamic_optimized_20261013.sql` | MOVE | `benchmarks/dynamic_optimized_20261013.sql`; measured candidate is retained separately from current production functions. |
| `benchmarks/queries/README.md` | MERGE, DELETE | `benchmarks/README.md` documents fixed workloads, archived SQL, and reproduction. |
| `reports/index_benchmark/indexes.sql` | MOVE | `database/indexes.sql`; preserve all four existing approved DDL statements byte-for-byte. Date-index benefit remains uncertain, not silently removed. |
| `reports/index_benchmark/{README.md,summary.csv,measurements.csv,environment.json,validation.json}` | MOVE | `reports/sql_optimization/`; measurement/metadata contents remain unchanged. Update only explanatory Markdown links. |
| `reports/index_benchmark/plans/*.txt` | KEEP/MOVE | Ten representative plans remain visible under the new report; move two less informative scan baselines to its ignored `raw/omitted_plans/`. |
| `reports/dynamic_reports/{README.md,*.csv,*.json}` | KEEP | Complementary five-function experiment, not a duplicate of the eight-query benchmark. Preserve measured results and historical provenance. |
| `reports/dynamic_reports/plans/*.txt` | KEEP/GITIGNORE | Keep seven monthly/daily/top-brand plans illustrating rewrites, selective indexes and regression. Move eight others to ignored `raw/omitted_plans/`. |
| Both benchmark `raw/**` trees | GITIGNORE | Preserve full captures locally for optional report regeneration; omit from portfolio output. |
| `reports/sql_baseline/environment.json`, `query_summary.json` | MOVE | `reports/sql_optimization/baseline/`; retain compact single-run evidence distinctly from controlled medians. |
| `reports/sql_baseline/data_verification.json`, `table_counts.json` | MOVE | `reports/data_validation/`; preserve source-file validation evidence independently of benchmark plans. |
| Remaining `reports/sql_baseline/**` | MOVE/GITIGNORE | Preserve original report, complete result exports and duplicate JSON/TXT plans in `reports/sql_optimization/raw/baseline/`; superseded details remain available locally. |
| `scripts/benchmark_sql_optimization.py`, `benchmark_dynamic_reports.py` | KEEP | Read centralized fixed cases/SQL/index DDL. Standardized directories and deliberate in-place replacement prevent accumulating result folders. Protect validated historical evidence from accidental overwrites. |
| `scripts/snapshot_queries.py`, `verify_dataset.py` | KEEP | Still useful; update canonical example and validation-output paths. Snapshotting preserves single-run versus median distinctions. |
| `scripts/migrate_to_monthly_partitions.py`, `compare_query_plans.py` | MOVE/REVIEW | `experiments/partitioning/`; preserve as experiments. Composite uniqueness breaks current UPSERT targets; dependencies/views and rollback recovery need isolated rehearsal before any approval. Never execute during cleanup. |
| Existing unit/integration/performance test layout | KEEP | Update paths and add focused structure/provenance checks; retain generator and loader tests. |
| Root `Specification.md` | MOVE | `docs/course_assignment.md`; course partitioning requirement is retained and explicitly still outstanding. |
| Root README and technical READMEs | MERGE/KEEP | Root becomes a short entry point linking reporting catalog, benchmark and generator/loader documentation. |
| `pyproject.toml`, `uv.lock`, Compose, configuration example | KEEP | Preserve the two console entry points and current external PostgreSQL volume. |
| `data/**`, local credentials, dumps, raw plans, caches, logs/editor files | GITIGNORE | Generated/local content stays on disk and out of Git. Exceptions retain summary/measurement CSVs. |
| Unknown local configuration under hidden environment directories | REVIEW | Do not inspect secrets or delete uncertain files. No application dependency was found. |

## Preservation and validation

`cleanup_provenance.json` records retained SQL/result artifacts with their old and
new paths and SHA-256 digests. Tests verify their contents after migration, plus
the historical original/rewrite hashes already recorded in benchmark validation.
Removed source files are only confirmed duplicates whose statements now exist
in named SQL blocks. Generated plan files are moved, not destroyed.

The schema link preserves installed-loader compatibility. No packaged code,
business logic, schema constraints, source database records, or approved index
membership changes as part of this restructuring.

## Completed validation

- Full suite: **72 tests passed**, including 35 reporting and 14 loader
  PostgreSQL integration tests; temporary schemas isolate all fixture writes.
- All 34 retained artifact hashes match; original analytical/rewrite hashes and
  the measured dynamic candidate hash remain unchanged.
- Both report-only generators executed on temporary copies of saved captures:
  all 120 analytical and 75 dynamic query measurements, and all summary medians,
  were retained. Generated outputs contain the configured 10 + 7 plans.
- The historical analytical CSV has padded headers/cells. The shared reader now
  normalizes that padding on read, preventing lost metrics during regeneration;
  the original CSV remains byte-identical. A regression test covers JSON cells.
- Python compilation, CLI help checks, local Markdown links, Git whitespace,
  raw/data ignore rules, and measurement/source exceptions were checked.
- Read-only source catalogs confirmed ordinary unpartitioned order tables and
  all four existing performance indexes. No expensive benchmark, dataset
  regeneration, source DDL change, or partition migration was performed.

The 16 generated baseline plan files and obsolete generated README were removed
from Git tracking only after their local archived copies were verified. The
cleanup stages those specific removals; other changes remain available for
normal review and commit. Unknown local files were preserved.

Follow-up decisions: isolate the date index's contribution before considering
removal; review and rehearse partitioning on an isolated clone if completing the
course requirement. Neither decision blocks the repository cleanup.
