# PostgreSQL Loading and SQL Performance Evaluation

## Overview

The evaluation compares two full-dataset loading strategies and three SQL
optimization configurations on 22,534,615 business records. It measures ingestion
time, storage, SQL rewriting, and the read/write trade-offs of four workload indexes.
Measurements were collected October 15–16, 2026 (Asia/Ho_Chi_Minh).

Loading before index creation reached the indexed state in **456.74 seconds**,
versus **560.00 seconds** with indexes maintained throughout loading. Selective
product-item lookup improved **32.28×**, while broad seller performance became
**40.3% slower** with its index-based plan. A correlated seller/date query also
regressed substantially. The results favor workload-specific engineering decisions.

## Experimental environment

- PostgreSQL 16.15 in Docker; Intel i7-11800H, 16 logical CPUs, approximately
  31 GiB RAM, no swap. Docker has no explicit CPU/memory cap and 1 GiB shared memory.
- `shared_buffers=128 MiB`, `work_mem=4 MiB`, `maintenance_work_mem=64 MiB`,
  at most two parallel workers per gather, JIT on. Durability settings remained on.
- **22,534,615 business rows**, from **107 CSVs / 2.70 GiB**: 5,000,000 orders,
  17,500,990 items, and 33,625 reference/dependent rows.
- Two fresh databases used the same schema, inputs, loader, transaction boundaries,
  and final index definitions. Required PK, UNIQUE, FK, and CHECK constraints stayed
  enabled throughout. No partitioning or new optimization was introduced.
- Only one large benchmark database existed at a time. Approximately 21.8 GiB was
  initially free; a 4 GiB disk reserve was checked before loads and queries.
  No unrelated client workload was present at preflight.

```text
A1: initialize → load → B1/B2 queries → build four indexes → B3 queries → remove DB
A2: initialize → build the same four indexes → load → verify → remove DB
```

Both databases were verified before removal. The primary `ecommerce_oltp` database
was accessed read-only and remained unchanged. Source files also remained unchanged.
Exact versions, settings, source hashes, file checksums, and parameters are in
[environment.json](environment.json); correctness evidence is in
[validation.json](validation.json).

## Benchmark methodology

### Loading strategies

The unchanged production loader uses batched `execute_values` UPSERTs for seven
small/medium tables, with a 10,000-row page size. Each order/item part uses
`COPY → unlogged staging → ordered final-table UPSERT → staging truncate`.
Each CSV/part is one transaction, including its SHA-256 checkpoint. All 107 files
loaded successfully in each scenario; none was skipped or retried.

Index builds used the exact `CREATE INDEX CONCURRENTLY` statements from
[database/indexes.sql](../../database/indexes.sql), separately in autocommit mode.
Initialization includes database creation, application DDL, and installation of
the current reporting functions in the isolated database.
Phase durations use `time.perf_counter()` around unchanged production APIs;
interpreter/uv startup is excluded. Source hashes identify the exact implementation
used for the measurements.

### SQL configurations and repetitions

| Stage | SQL | Additional performance indexes |
|---|---|---|
| B1 | Original baseline SELECTs | None |
| B2 | Current canonical function bodies, rendered as standalone SELECTs | None |
| B3 | Exactly the same SQL and parameters as B2 | All four approved indexes |

Every case/stage used one excluded warm-up and **five measured executions** of
`EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS, FORMAT JSON)`. B1/B2 executions were
interleaved in randomized rounds; B3 case order was also randomized. Seeds were
42–47. Tables were vacuumed/analyzed before B1/B2 and analyzed after index creation.
The no-index stages genuinely lacked the four indexes; index scans were not disabled.

There are **17 parameter cases for 12 functions**, covering all 13 original
requirements plus broad/filter contrasts. All-history analytical baselines retain
their original scope; current functions receive infinite date bounds for those
cases. Dynamic reports use January 1–June 1, 2025, end exclusive. Selective cases
use products/sellers/brands 1–2 and categories 6–7 as applicable; the seller-order
listing uses seller 1 in March. Top-N is 5 per brand, 20 globally, and 1 for the
highest order. Categories 1–5 contain no products, so 6–7 avoid empty filter tests.
Full per-case parameters are recorded in [summary.csv](summary.csv).

### Correctness checks

- Authentic SELECTs are preserved in
  [original_queries.sql](../../database/reporting/original_queries.sql), recovered
  from Git `fc35293`'s analytical SQL and original dynamic-function bodies. Only
  dynamic parameter literals are substituted. Optimized
  [functions.sql](../../database/reporting/functions.sql) and
  [queries.sql](../../database/reporting/queries.sql) are the canonical implementation.
- Bidirectional `EXCEPT ALL` returned **zero differences for all 17 cases**.
  Some original dynamic reports use order dates while current ones use item dates;
  all 17.5M items match their parent timestamp. This is dataset-specific equivalence,
  not a new schema invariant or a claim of universal equivalence.
- The March seller case adds March bounds to the authentic richer seller-summary
  SELECT, comparing like-for-like columns. The six-column March seller projection
  was validated separately, also with zero differences; it is not timed against
  a richer result and presented as the same query.
- Both loads have identical counts and two seeded, order-independent full-row
  hash sums for every business table, excluding only load-time `loaded_at`.
  This is a strong probabilistic fingerprint, not a mathematical set-equality
  proof. All 56 constraints are validated, all 29 application indexes are valid,
  and final column/constraint/index definitions match.
- Checkpoints match every source checksum/count; staging tables are empty.
  Customer/product timing and order-total checks found zero violations. **109
  existing tests passed**, with real integration connections confined to A2 test
  schemas. Fixture schemas were removed and business fingerprints rechecked.

## Data loading performance

| Metric | A1: load → index | A2: index → load |
|---|---:|---:|
| Initialization | 0.119 s | 0.093 s |
| Data loading | 434.974 s | 559.899 s |
| Performance-index creation | 21.649 s | 0.009 s |
| Time to indexed state: phase sum | **456.742 s** | **560.001 s** |
| Business rows loaded | 22,534,615 | 22,534,615 |
| Loading throughput | 51,807 rows/s | 40,248 rows/s |
| Final database size | 6.83 GiB | 8.19 GiB |
| All application indexes | 3.93 GiB | 5.29 GiB |
| Four performance indexes only | 2.28 GiB | 3.64 GiB |

These are **one complete run per strategy**, not medians. The total sums measured
initialization, loading, and index-build durations; it excludes the interleaved
query experiment, statistics maintenance, verification, fixture tests, and cleanup.
Data generation is excluded from both scenarios. Size snapshots precede fixture
tests, so temporary test-catalog allocations do not affect the comparison.

### Per-table loading time

| Table | Rows | A1 seconds | A2 seconds |
|---|---:|---:|---:|
| brand | 20 | 0.003 | 0.003 |
| category | 25 | 0.002 | 0.002 |
| seller | 50 | 0.003 | 0.003 |
| customer | 30,000 | 0.938 | 1.038 |
| product | 3,000 | 0.117 | 0.140 |
| promotion | 30 | 0.004 | 0.005 |
| promotion_product | 500 | 0.014 | 0.016 |
| order | 5,000,000 | **78.024** | **130.632** |
| order_item | 17,500,990 | **355.854** | **427.978** |

Table times sum individual file-handler durations; whole-load time also includes
orchestration overhead. Exact phase/table measurements are in [loading.csv](loading.csv).
Sub-second small-table differences are not credible evidence of index overhead.

Maintaining the four additional indexes increased whole-load time by **28.7%**:
orders took **67.4%** longer and items **20.3%** longer. Building afterward cost only
21.65 seconds, making A1 **18.4% faster overall** in this experiment. Its performance
indexes occupied **1.36 GiB less space**. Insertion/build layouts and page splits
are plausible explanations; page density and dead-tuple bloat were not measured.
These are bulk-loader costs, not concurrent OLTP write-TPS results.

**Initial-load recommendation:** load first, then build the approved performance
indexes, while keeping all required integrity/UPSERT indexes enabled.

## SQL optimization results

### Median execution times, milliseconds

Speedups are **B1/B2**, **B2/B3**, and **B1/B3** respectively; below 1× means slower.

| Case | B1 original | B2 current | B3 current + indexes | SQL speedup | Index speedup | Overall |
|---|---:|---:|---:|---:|---:|---:|
| monthly_items | 9,712.974 | 7,488.633 | 7,858.413 | 1.30× | 0.95× | 1.24× |
| daily_selective | 741.361 | 756.643 | 175.476 | 0.98× | 4.31× | 4.22× |
| seller_performance_selective | 1,278.370 | 1,344.101 | 782.270 | 0.95× | 1.72× | 1.63× |
| top_brand_selective | 1,725.385 | 1,843.303 | 1,186.946 | 0.94× | 1.55× | 1.45× |
| status_selective | 1,616.228 | 1,623.068 | 760.032 | 1.00× | 2.14× | 2.13× |
| monthly_orders | 2,575.464 | 2,626.897 | 2,662.739 | 0.98× | 0.99× | 0.97× |
| orders_seller_march | 1,339.076 | 134,816.318 | 2,144.684 | 0.01× | 62.86× | 0.62× |
| items_product | 277.171 | 275.213 | 8.526 | 1.01× | 32.28× | 32.51× |
| highest_order | 645.578 | 681.777 | 0.036 | 0.95× | 18,938.25× | 17,932.72× |
| top_products | 5,012.196 | 4,253.690 | 4,312.593 | 1.18× | 0.99× | 1.16× |
| seller_sales | 15,607.616 | 13,356.639 | 13,761.205 | 1.17× | 0.97× | 1.13× |
| product_month | 9,064.497 | 7,638.404 | 8,044.729 | 1.19× | 0.95× | 1.13× |
| daily_broad | 9,325.474 | 7,123.882 | 7,189.149 | 1.31× | 0.99× | 1.30× |
| seller_performance_broad | 14,567.571 | 9,065.744 | 12,723.345 | 1.61× | 0.71× | 1.14× |
| top_brand_broad | 5,771.921 | 5,398.864 | 6,072.712 | 1.07× | 0.89× | 0.95× |
| status_broad | 555.637 | 530.019 | 542.429 | 1.05× | 0.98× | 1.02× |
| seller_sales_march | 4,657.483 | 4,242.427 | 4,492.012 | 1.10× | 0.94× | 1.04× |

[summary.csv](summary.csv) also contains min/max and p25/p75. All individual runs,
including labeled warm-ups, planning times, buffer/temp blocks, index names,
node types, hash batches/build loops, and worker counts are in
[measurements.csv](measurements.csv). Root buffer counters are cumulative; do not
sum them across parent/child nodes. Buffer reads are PostgreSQL cache misses,
not necessarily physical device reads.

### Functions versus standalone SQL

All 17 cases were also checked through actual PostgreSQL function calls in B2/B3.
Six cases per stage had different node shapes and received their own excluded
warm-up plus five measured function calls. Several differences are additional
`Subquery Scan` wrappers; product/month is more substantive: the callable plan
joins aggregated products through `product_pkey` using nested loops rather than
the standalone plan's final hash join.

| Shape-different function case | B2 function median ms | B3 function median ms |
|---|---:|---:|
| top_brand_selective | 1,931.044 | 1,156.812 |
| status_selective | 1,693.073 | 751.655 |
| highest_order | 704.204 | 0.013 |
| product_month | 7,806.114 | 7,625.318 |
| top_brand_broad | 5,675.613 | 6,022.827 |
| status_broad | 582.895 | 601.901 |

These separate trials are not mixed into the main table. Matching shapes had
only a one-off diagnostic, not a claimed function median. The seller/date function
reproduced B2 at **138,594.612 ms** and B3 at **2,069.487 ms**. Complete reports are
measured without the CLI's default 50-row limit; network/CSV-export time is excluded.

## Index cost-benefit analysis

[database/indexes.sql](../../database/indexes.sql) remains the single DDL source.
All four are partial composite B-trees on non-deleted rows. They were enabled as
a set: neither query speedups nor loading overhead isolate an individual index.

| Performance index | A1 MiB | A2 MiB | Recommendation and observed role |
|---|---:|---:|---|
| order_item_active_product_idx | 1,579.37 | 2,852.70 | **Keep for selective workloads.** Item lookup, daily/seller filters and filtered brand ranking benefit. Largest storage/write cost; also contributes to the poor broad seller plan. |
| order_active_amount_idx | 395.55 | 513.84 | **Keep if highest-order ranking matters.** Supplies the ordered one-row access path. |
| product_active_seller_idx | 0.086 | 0.125 | **Keep.** Very small; supports seller/product access and the one-time seller-product hash in indexed order listing. |
| order_active_date_idx | 361.07 | 362.23 | **Needs independent evaluation; conditional removal candidate.** Used by March order listing and seller sales, but the latter does not improve. Isolated value is not established. |

There is no obvious duplicate leading-key responsibility: date and amount indexes
serve different orderings; product-leading item access is not replaced by the
required `(order_id, product_id)` constraint index. Shared INCLUDE columns still
cost storage. Keep all constraint-backed indexes: PK/UNIQUE integrity and
business-key UPSERT depend on them.

No primary index was removed. Before dismissing the date index or narrowing the
wide item index, measure independent ablation and actual report frequency. Evaluate
the seller/date query shape first; adding indexes to every broad aggregate or
proceeding directly to partitioning is not justified by this experiment.

## Execution plan insights

- **Monthly item revenue:** the deleted-parent anti-join avoids joining every live
  order. The representative hash falls from 64 batches to 1; temporary reads drop
  from 240,118 to 135,266 blocks. Distinct-order sorting over 17.5M items remains.
  The broad indexed plan uses no additional index and adds no convincing benefit.
- **Daily revenue:** the same anti-join improves broad reporting by 1.31×. With
  products 1–2, bitmap item access plus order-PK probes gives a further 4.31× gain.
  Distinct-order aggregation and parent lookups still cost time.
- **Seller performance:** early seller aggregation/anti-join improves broad B2 by
  1.61×; selective access benefits from indexes. Broad B3 instead chooses 3,000
  item-index probes, nested-loop anti-join, and a largely serial incremental sort
  over 17.5M rows. Its workers only scan deleted orders. Temporary reads halve to
  67,777 blocks, yet latency rises **40.3%**. Less I/O and index-only scans do not
  guarantee a faster plan.
- **Top products per brand:** the SQL filters products/brands before
  aggregation, then ranks the aggregated product totals within each brand.
  The filtered indexed case improves 1.55×. Broad B2/B3 retain the same parallel
  hash-join/window-ranking shape, with 64 hash batches and about 108,580 temporary
  read blocks; neither uses an additional index. Its 12.5% stage slowdown cannot
  be attributed to index traversal. Ranges overlap; there is no demonstrated
  general broad-query improvement. Top-N cannot avoid aggregating the input.
- **Status summary:** the EXISTS-based logic is essentially unchanged. NULL
  filters remove the item test, leaving an order scan/aggregate. Selective item
  qualification gains 2.14× with indexes but still scans parent orders.
- **Monthly full-order revenue:** no substantive rewrite. It still scans 5M
  orders and performs an external sort of roughly 118 MiB. Broad date coverage
  gives no useful additional-index advantage.
- **Orders by seller/date:** original direct EXISTS has a parallel semi-join.
  Current optional-filter SQL gets a correlated SubPlan with **1,026,526**
  executions, repeatedly scanning products; B2 is about **100.7× slower**. B3 uses
  a date-covering scan and hashes 63 seller products once, reversing the repeated
  join's build/probe sides. That rescues 62.86× but remains slower than B1.
  This is a SQL/planner-shape issue, not evidence that partitioning is required.
- **Items by product:** the no-additional-index plan scans the constraint index
  whose leading column is `order_id`. B3 uses the product-leading covering index,
  with zero heap fetches and a small in-memory sort for 25,154 output rows: 32.28×.
- **Highest-value order:** an amount-ordered index-only scan stops after one row,
  replacing the large scan/top-N sort. The extreme ratio uses a **0.036 ms**
  denominator; it is not an end-to-end API/CLI speedup.
- **Global top products:** pre-aggregate before joining product labels; that join
  now processes product totals instead of millions of lines. The parent order
  hash join still spills into 64 batches, limiting the SQL gain to 1.18×.
  The additional indexes do not help this all-history plan.
- **Seller sales, all history/March:** aggregate before joining seller labels,
  but multiple DISTINCT counts and large sorts remain. March uses the date index
  in B3 without improving its median; full-history B3 uses no additional index.
- **Product/month revenue:** aggregate narrow month/product keys before attaching
  labels. Temporary reads fall from 449,596 to 248,666 blocks, but the parent join
  still has 64 hash batches. B3 uses no additional index; its small stage slowdown
  has overlapping timing ranges.

## Key findings and engineering decisions

- **Initial bulk loading:** load before building performance indexes. Keep
  constraint-backed indexes enabled; file transactions and checksums remain unchanged.
- **Selective reporting:** retain product-leading item access, ordered amount
  access, and the small seller-leading product index when these workloads matter.
- **Date index:** evaluate independently before removal; combined-index tests
  establish plan usage but not its isolated latency contribution.
- **SQL shape first:** investigate the seller/date correlated subquery and the
  broad seller plan's serial work before adding indexes or choosing partitioning.
- **Scope of evidence:** broad scans, DISTINCT aggregation, and spill costs remain.
  These measurements do not establish a partitioning benefit or production capacity.

## Limitations

- Query medians have five samples, not confidence intervals. Min/max and quartiles
  accompany them. Small differences with overlapping ranges are not optimization
  proof. Broad brand reporting has the same plan but stage variation; not every
  B2/B3 difference can be attributed to index access.
- Caches were warm; OS caches were not reset. Stages ran sequentially. Fresh
  ANALYZE samples, background activity, and thermal/cache history may affect results.
  A1 index building also followed the query experiment. Loading ran A1 then A2 once;
  these results are directional, not stable production capacity estimates.
- Generation time is outside the loading measurements. Partitioning, new
  indexes, materialized summaries, and alternative loader implementations are
  outside this evaluation. Full raw-plan dumps are not distributed; the compact
  metrics and three representative plans are the retained execution evidence.

## Reproduction and evidence

Use **new disposable database names** and a separate local INI configuration—never
point destructive setup at the primary database. Do not truncate or disable
constraints. After creating each empty database with PostgreSQL tooling:

```bash
uv sync
uv run ecommerce init-db --config benchmark.ini
uv run ecommerce load --config benchmark.ini --data-dir data --skip-schema
```

For A1, run the recorded B1/B2 cases before executing each statement from
`database/indexes.sql` in autocommit mode. For A2, execute them before loading.
Deploy `functions.sql` only in disposable databases when testing function calls.
Measure load/index phases separately. Repeat the recorded parameter cases, seeds,
excluded warm-ups and five trials; medians come from
`EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS, FORMAT JSON)`, not export duration.
The [reporting catalog](../../database/reporting/README.md) explains parameters
and semantics. Reproduction follows this procedure manually; no benchmark orchestration
framework is part of the application. Do not accidentally execute every
original SQL block against a busy database.

### Retained evidence

| Artifact | Purpose |
|---|---|
| [loading.csv](loading.csv) | Exact per-table, initialization, index-build and total timings |
| [summary.csv](summary.csv) | 17 cases, parameters, medians/ranges/quartiles and speedups |
| [measurements.csv](measurements.csv) | 306 standalone trials plus 72 function trials, including warm-ups |
| [environment.json](environment.json) | Hardware/settings, source/input hashes, index sizes, parameters and function diagnostics |
| [validation.json](validation.json) | Counts/fingerprints, checkpoints, SQL equivalence, tests, primary preservation and cleanup |
| [Seller/date B2 plan](plans/b2_orders_seller_march.txt) | The correlated-subquery regression |
| [Product-item B3 plan](plans/b3_items_product.txt) | Selective covering-index access, zero heap fetches |
| [Broad seller B3 plan](plans/b3_seller_performance_broad.txt) | Index traversal with a serial, spilling aggregation bottleneck |

Exactly three representative plans are retained. Loop/hash-build CSV details
apply to standalone captures; those fields are blank for callable trials whose
individual full plans were not retained. Their execution-time/buffer metrics were
recorded. No large raw-plan archive or benchmark dependency was added to source.
