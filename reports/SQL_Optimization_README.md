# PostgreSQL SQL Optimization — Faster Queries, Fewer Indexes

**PostgreSQL 16 | 22.53 million synthetic rows | 12 reporting functions | 37 benchmark cases**

This project explores a practical database question:

> **When does a faster query justify another index on an OLTP database?**

I improved the SQL first, measured the effect of additional indexes, and then reviewed those indexes against a realistic business scenario. **The recommendation is two optional indexes (C1 + C2), not the seven-index configuration that performed best in the original tuning experiment.** This is a design recommendation based on historical measurements; it has not been deployed.

## 1. The business problem

The dataset represents **five months** of transactions for a hypothetical mid-sized e-commerce platform:

| Dataset | Size |
|---|---:|
| Orders | 5,000,000 |
| Order items | 17,500,990 |
| Sellers | 50 |
| Products | 3,000 |

PostgreSQL is primarily an **OLTP database**: it must keep accepting orders and updating operational data. A small internal team also runs reports directly against it. In this scenario, the business has not yet built a separate data warehouse.

To make index decisions, I assume three reporting workflows. **A session runs several SQL queries; it is not one query.** These frequencies and workflows are illustrative, not production logs.

| Workflow | Sessions/day | Queries/session | Total queries/day | Purpose |
|---|---:|---:|---:|---|
| Management summary | 4 | 5 | 20 | Review broad sales and performance reports |
| Seller drill-down | 18 | 4 | 72 | Investigate individual sellers, brands, orders, and statuses |
| Rankings review | 4 | 3 | 12 | Review valuable orders and top products |
| **Total** | **26** | | **104** | |

**Business priorities:** Seller drill-down should feel responsive because analysts perform several operations in sequence. Broad summaries are less frequent and can be scheduled. A lookup that already takes a few hundred milliseconds usually does not need an index just to become even faster. **OLTP write performance and index maintenance matter too.** These are engineering assumptions, not measured service-level objectives (SLOs).

## 2. What did optimization actually improve?

I tested three stages:

- **B1 — Original SQL:** Starting queries, with only mandatory database indexes.
- **B2 — Rewritten SQL:** Improve joins, filters, and repeated work **before** adding reporting indexes.
- **Index experiments:** Add indexes one at a time and inspect how query plans change. The tables show both the intermediate **C1+C2** configuration and the historical **seven-index B3** result.

The tables below use **seconds per SQL execution**, except where milliseconds are written explicitly. They are medians from the saved primary benchmark runs. The intermediate C1+C2 stage is shown for context, not presented as a new official B3 run.

### A. Selective queries — the clearest reason to add an index

These queries narrow their results to a seller, brand, category, or time period. Without a suitable access path, they may scan many unrelated order items.

| Query case | B1: Original | B2: Rewritten | C1+C2 | Seven-index B3 |
|---|---:|---:|---:|---:|
| `status_medium_month` | 141.686 s | **1.302 s** | 0.436 s | 0.388 s |
| `seller_performance_selective` | 1.402 s | 1.380 s | **0.152 s** | 0.144 s |
| `top_brand_selective` | 1.822 s | 1.985 s | **0.390 s** | 0.365 s |
| `orders_seller_march` | 1.339 s | 1.401 s | **0.545 s** | 0.505 s |

**What changed?** The SQL rewrite fixed a particularly expensive status query: the original plan repeated work over one million times, while B2 used a set-based approach and a hash semi-join. Index **C2** then gave several other selective queries a direct path through `product_id`, often using an index-only scan instead of reading large parts of `order_item`.

**The lesson:** SQL rewriting and indexing solve different problems. A query can be slow because of its logic, its access path, or both.

### B. Broad queries — faster SQL does not remove the cost of scanning millions of rows

These reports summarize large portions of the dataset. A sequential scan may still be the right plan when most rows contribute to the result.

| Query case | B1: Original | B2: Rewritten | C1+C2 | Seven-index B3 |
|---|---:|---:|---:|---:|
| `seller_performance_broad` | 15.383 s | **9.843 s** | 9.520 s | 8.670 s |
| `seller_sales` | 16.404 s | **13.891 s** | 13.615 s | 15.866 s |
| `monthly_items` | 9.790 s | **7.937 s** | 7.823 s | 5.638 s |
| `monthly_orders` | 3.020 s | 2.914 s | 3.047 s | **0.990 s** |
| `product_month` | 10.259 s | **8.275 s** | 8.126 s | 10.178 s |

**What changed?** SQL rewriting reduced unnecessary work in several large reports. Additional month-based covering indexes also helped particular aggregations: for example, C4 removed a sort from `monthly_orders`, while C5 removed a large external sort from `monthly_items`.

**The trade-off:** Those extra indexes consume hundreds of MiB each, and broad queries still process substantial data. Some seven-index timings were slower despite similar execution plans; the benchmark also showed time-dependent variation, so these differences should **not** automatically be treated as index-caused regressions.

### C. Top-K queries — a huge speedup can still be unnecessary

Top-K queries are not all alike. Finding the largest *stored order amount* is different from ranking products by a total that must first be calculated.

| Query case | B1: Original | B2: Rewritten | C1+C2 | Seven-index B3 |
|---|---:|---:|---:|---:|
| `highest_order` | 0.659 s | 0.692 s | 0.663 s | **0.007 ms** |
| `highest_order_week` | N/A | 0.194 s | 0.200 s | **0.071 ms** |
| `top_products` | 5.042 s | **4.374 s** | 4.448 s | 5.218 s |
| `top_products_march` | N/A | 2.980 s | 2.971 s | 2.628 s |

**What changed?** C7 orders an index by `total_amount DESC`, allowing PostgreSQL to find the highest-value order and stop immediately. But `top_products` must aggregate sales before ranking them, so that same index cannot eliminate its main work.

**The decision:** Moving `highest_order` from roughly **692 ms to 0.007 ms** is technically impressive. Yet the original lookup was already under one second, and this workflow is used infrequently. That alone does not justify maintaining another **150 MiB** index.

## 3. The decision: why keep only two indexes?

I evaluated all nine tested candidates using four questions:

1. **Need:** Was the query or workflow actually too slow for its business purpose?
2. **Evidence:** Did the index solve that problem, as shown by execution plans and absolute time savings?
3. **Cost:** Is the benefit worth the index's disk space and ongoing OLTP write maintenance?
4. **Stop:** Is performance already good enough without more indexes?

### Business impact of the tested configurations

The same assumed workflow was applied to existing benchmark medians. Session figures are **sums of SQL execution times**, not measured dashboard response times.

| Reporting workload | B2: No optional indexes | C1+C2 | Seven-index B3 |
|---|---:|---:|---:|
| **Seller drill-down / session** | **6.238 s** | **1.550 s** | 1.387 s |
| Management summary / session | 42.860 s | 42.130 s | 41.342 s |
| Rankings review / session | 8.045 s | 8.082 s | 7.846 s |
| **All reporting / day** | **315.903 s** | **228.751 s** | **221.718 s** |
| **Additional index storage** | **0 MiB** | **826.602 MiB** | **2,233.844 MiB** |

**Why this matters:** C1+C2 reduces the repeated seller drill-down workflow by an observed **4.688 seconds per session** compared with B2. Adding five more indexes costs roughly **1,407 MiB** and changes the modeled daily total by only **another 7.033 seconds** in the historical captures. Those differences are scenario estimates subject to benchmark drift, not precisely measured causal effects or CPU cost.

### Index-by-index decisions

| Index | Size | What the tests showed | Decision and reason |
|---|---:|---|---|
| **C1 — `order_order_id_deleted_idx`** | 8 KiB | Avoids unnecessary deleted-parent checks; targeted tests support the gain. | **Keep, provisionally.** Very low current cost. Its additional value once C2 exists has not been isolated. |
| **C2 — `order_item_product_order_cover_idx`** | 827 MiB | Seller performance fell from **1.195 s to 0.152 s** when added; multiple selective plans improved. | **Keep, provisionally.** It solves a repeated interactive bottleneck, despite substantial storage and write maintenance. |
| C3 — seller/product partial index | 0.09 MiB | Changed broad seller performance to a slower serial nested-loop plan. | **Reject.** A smaller index is not useful if it selects a worse plan. |
| C4 — order/month covering index | 236 MiB | Monthly orders improved by about **2.0 s**, but the March variant became slower. | **Omit.** A real gain, but the report runs infrequently and is not a priority interactive workflow. |
| C5 — item/month covering index | 827 MiB | Monthly items improved by about **1.7 s**, avoiding a large sort. | **Omit.** A second wide fact-table index is costly for a report that remains several seconds long. |
| C6 — order/date covering index | 193 MiB | Improves some date-filtered requests by hundreds of ms; one monthly aggregation regresses. | **Omit.** Its strongest targets were mostly fast enough or outside the main workflow. |
| C7 — order/amount index | 150 MiB | Turns an already-subsecond highest-order lookup into a near-instant result. | **Omit.** Very large speedup, limited business need. |
| C8 — item/date BRIN index | 96 KiB | Speeds up weekly item reporting, with a small regression in one export. | **Omit by default.** Cheap and worth revisiting if weekly reporting becomes common. |
| C9 — second wide item covering index | 827 MiB | Not used in any of its 370 captured trial executions. | **Reject.** No demonstrated read benefit to offset maintenance. |

**The resulting recommendation is C1+C2, plus the 25 mandatory PK/UNIQUE indexes.** It is the smallest *historically measured* configuration I judged sufficient for the assumed interactive workflow—not proof of the globally smallest or fastest possible configuration. C2 alone was not benchmarked.

**Important implementation distinction:** The recommendation has **not** been deployed. [`database/indexes.sql`](../../database/indexes.sql) still contains the **historical seven-index B3 definitions**; running it would not install only C1+C2.

## 4. How the measurements were made

- **Environment:** PostgreSQL 16.15, isolated physical database copy; Intel i7-11800H, ~31 GiB RAM, `shared_buffers=128 MiB`, `work_mem=4 MiB`, up to two parallel workers per gather, JIT enabled.
- **Protocol:** For each fixed SQL case, three consecutive warmups followed by **seven measured runs**. The reported value is the median of those seven runs.
- **Plans and resource use:** `EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS, FORMAT JSON)`.
- **Fair baseline:** B1 and B2 had no optional reporting indexes, but kept all **25 mandatory PK/UNIQUE indexes**. No index-scan planner settings were disabled to simulate a baseline.
- **Correctness:** All **28 comparable** B1/B2 cases passed a two-way `EXCEPT ALL` result check. Nine cases had no original B1 counterpart.

The complete **37-case benchmark** covers **12 reporting functions**; the tables above show selected examples across Selective, Broad, and Top-K workloads. The historic equal-family benchmark score also decreased from **32,742.020 ms (B2)** to **27,487.573 ms (seven-index B3)**, but this score is **not a daily workload estimate** and was not the final index selection criterion.

### What the evidence does not prove

- **Real user latency:** Measurements cover standalone SQL execution, not application requests, network transfer, parallel dashboard calls, or [parameterized reporting-function](../../database/reporting/functions.sql) invocation time.
- **OLTP write cost:** C2 must be maintained for newly inserted active items. Its effect on write latency, WAL volume, bloat, and concurrency was **not measured**. The five-month dataset implies roughly **117,000 item rows/day** as an illustrative average, not verified production insert traffic.
- **Exact benefit of each index:** Different configurations were measured at different times. The same seven-index set differed by **2.608 s** on the historical equal-family score between two measurements, even with similar plan shapes. Confirmation tests help explain targeted effects but do not eliminate this drift.
- **Actual business frequency:** The 26 sessions/day are a declared assumption. If reports become more interactive or OLTP contention appears, the index decision should be revisited.

For infrequent broad reports that still take **8–14 seconds**, the next step may be scheduling, caching, or pre-aggregation rather than adding wider indexes. A dedicated analytical system becomes relevant if reporting demand grows; it is not assumed necessary here.

## 5. Related evidence and repository files

- [Original SQL (B1)](../../database/reporting/original_queries.sql) · [Rewritten SQL (B2)](../../database/reporting/queries.sql) · [Reporting functions](../../database/reporting/functions.sql)
- [Historical index definitions](../../database/indexes.sql) · [Benchmark evidence guide](evidence/README.md) · [Repository guidance](../../AGENTS.md)

**Separate loading experiment:** With a *different* fixed four-index setup, loading data first and creating indexes afterward took **456.742 s**, versus **560.001 s** when those indexes were maintained during loading. This supports a bulk-load engineering decision; it is **not** a measurement of C1+C2's live OLTP write overhead.

---

**Takeaway:** The most valuable optimization was not the largest speedup. It was learning to **fix expensive SQL, recognize when an index genuinely helps, and stop adding indexes when the business benefit no longer justifies their cost**.
