# Partitioning experiment — not deployed

The current production schema is unpartitioned. These scripts are preserved
course-assignment work, not part of schema setup, `generate`, `load`, or either
SQL benchmark. No partition migration was executed during repository cleanup.

`migrate_to_monthly_partitions.py` proposes January–May 2025 range partitions
for orders and items. It validates the date window, takes exclusive table locks,
copies records, changes PK/UNIQUE/FK keys to include `order_date`, swaps table
names, synchronizes sequences, creates an experimental product index, and drops
the old tables in one transaction. It needs substantial disk/WAL capacity.

**Do not run it against the configured source database.** Its composite business
uniqueness is incompatible with the production loader's current `ON CONFLICT`
targets. Cross-month/global identity, dependent views, FK assumptions, staging,
checkpoints and recovery need review. The experiment's `order_item_product_id_idx`
is not one of the four approved production performance indexes.

Before any approved experiment: make a backup; prepare an isolated clone;
configure the script exclusively for that clone; inspect dependent objects;
capture matching baseline queries; confirm order/item timestamps agree and all
rows fit the fixed window; then test load/report compatibility and rollback.
Direct script execution performs a migration; it has no `--help` parser.

`compare_query_plans.py` is an offline comparison utility. It expects historical
single-run summary metadata under `reports/sql_optimization/baseline/`, optional
raw plans/result CSVs under `reports/sql_optimization/raw/baseline/`, and
post-experiment snapshots under local ignored `experiments/partitioning/results/`.
Those post-migration results do not currently exist. Fresh checkouts need new
baseline captures on an isolated clone before a meaningful comparison.

The [course assignment](../../docs/course_assignment.md) explicitly requests
partitioning and before/after plans. That requirement remains **outstanding**;
the existing unpartitioned index benchmarks do not fulfill it.
