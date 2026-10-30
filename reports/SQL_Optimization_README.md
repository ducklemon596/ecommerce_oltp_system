# PostgreSQL Query Optimization — Faster Where It Matters

**PostgreSQL 16 · 22.53 million synthetic records · 12 reporting functions · 37 benchmark cases**

**The goal:** Make reporting useful without slowing down the transactional system with indexes it does not need.

I first improved the SQL, then tested how different indexes changed query performance. The result is a practical recommendation: **keep two optional reporting indexes**, not all seven that were tested successfully for read performance.

> **Key decision:** The fastest query is not always worth an extra index. A good index must solve a real problem and justify its storage and ongoing maintenance.

## 1. The business problem

This project models five months of activity for a mid-sized e-commerce platform:

| Data | Volume |
|---|---:|
| Orders | 5,000,000 |
| Order items | 17,500,990 |
| Sellers | 50 |
| Products | 3,000 |

PostgreSQL serves customer transactions **and** internal reports. The company has no dedicated data warehouse in this scenario, so reports must run on the OLTP database without unnecessarily affecting everyday operations.

For the index decision, I assumed a small internal reporting team:

| Reporting workflow | Sessions/day | Queries per session | Queries/day |
|---|---:|---:|---:|
| Management summaries | 4 | 5 | 20 |
| Seller drill-down | 18 | 4 | 72 |
| Rankings review | 4 | 3 | 12 |
| **Total** | **26** | | **104** |

*A session may run several queries. These usage numbers are business assumptions, not production measurements.*

**What matters to the business:** Seller drill-down should feel responsive; management summaries are less frequent and can be scheduled. A lookup that already completes in under a second rarely needs another large index. Transactional writes remain the priority.

## 2. What improved?

The optimization has two steps:

1. **Rewrite SQL:** Fix inefficient joins, filters, and repeated computation before creating indexes.
2. **Test indexes:** Compare the SQL with no optional indexes, with the **recommended two-index set**, and with a **seven-index test configuration**.

The following values are **median SQL execution times** from the same benchmark round (October 30, 2026). Lower is better. They are not application response times.

### Selective queries — avoid reading unrelated rows

These reports filter by seller, brand, order status, or time period. An appropriate index can avoid scanning much of the `order_item` table.

| Query | Original SQL | Rewritten SQL | 2 indexes | 7 indexes |
|---|---:|---:|---:|---:|
| Seller performance (filtered) | 1.153 s | 1.150 s | **0.026 s** | 0.026 s |
| Brand ranking (filtered) | 1.368 s | 1.439 s | **0.149 s** | 0.147 s |
| Orders for a seller (March) | 1.255 s | 1.236 s | **0.415 s** | 0.380 s |
| Order status (filtered month) | 1.387 s | 1.268 s | **0.242 s** | 0.241 s |

**Why it works:** The product-leading covering index gives PostgreSQL a direct way to find relevant order items. The execution plans show targeted index access instead of scanning many unrelated rows. **Most of the useful gain is already achieved with two indexes.**

### Broad queries — SQL rewrites help, but large scans remain

These reports summarize millions of rows. Scanning much of a table is not necessarily a bad plan when the report needs much of its data.

| Query | Original SQL | Rewritten SQL | 2 indexes | 7 indexes |
|---|---:|---:|---:|---:|
| Seller performance (all sellers) | 14.439 s | **9.165 s** | 8.744 s | 8.753 s |
| Seller sales | 15.674 s | **13.043 s** | 12.851 s | 12.944 s |
| Item revenue by month | 10.591 s | **7.488 s** | 7.333 s | 5.481 s |
| Order revenue by month | 2.471 s | 2.537 s | 2.476 s | **0.999 s** |

**Why it matters:** Rewriting the SQL reduces unnecessary work without adding storage. Extra month-based indexes also speed up particular summaries, but some still take several seconds and the larger indexes must be maintained on every relevant write. For occasional management reports, scheduling or caching may be a better next step.

### Top-K queries — a huge speedup is not always useful

| Query | Rewritten SQL | 2 indexes | 7 indexes |
|---|---:|---:|---:|
| Highest-value order | 646 ms | 641 ms | **0.011 ms** |
| Highest-value order (week) | 190 ms | 174 ms | **0.014 ms** |
| Top products | 4.070 s | 3.991 s | 4.227 s |

An index ordered by `total_amount` lets PostgreSQL find the highest-value order almost immediately. **But the original lookup was already below one second**, and the extra index costs about **150 MiB**. Ranking products is different: PostgreSQL must first calculate sales totals, so the order-amount index does not solve that work.

## 3. The important decision: why stop at two indexes?

Instead of asking *“Which configuration has the lowest execution time?”*, I asked:

- **Need:** Is the query or workflow too slow for its actual use?
- **Evidence:** Does the index improve that problem in the execution plan?
- **Cost:** Is the benefit worth more storage and write maintenance?
- **Stop:** Is performance good enough without more indexes?

### Impact on the assumed daily workload

A reporting session contains multiple SQL operations. The times below **add up those SQL execution times**; they are not measured dashboard loading times.

| Metric | No optional indexes | **Recommended: 2 indexes** | 7-index test |
|---|---:|---:|---:|
| Seller drill-down / session | 4.995 s | **0.735 s** | 0.696 s |
| Management summary / session | 39.658 s | 39.116 s | 36.154 s |
| Rankings review / session | 7.344 s | 7.355 s | 6.691 s |
| Total report execution time / day | 277.915 s | **199.111 s** | 183.905 s |
| Extra index storage | 0 | **826.602 MiB** | 2,233.844 MiB |

**The trade-off:** The two-index configuration saves an observed **4.260 seconds per seller drill-down session**, where users are actively investigating data. Adding five more indexes requires **another 1,407 MiB** but cuts the modeled total by only **another 15.206 execution seconds per day**, mostly for infrequent summaries.

These are modeled estimates based on benchmark timings and assumed session frequencies—not measured user wait times or exact causal savings.

### Index decisions

| Index | Decision | Reason |
|---|---|---|
| `order_order_id_deleted_idx` (8 KiB) | **Keep, provisionally** | Helps avoid unnecessary deleted-order checks with minimal current storage; its necessity remains debatable. |
| `order_item_product_order_cover_idx` (826.6 MiB) | **Keep, provisionally** | Delivers the clearest improvement to repeated seller/brand drill-down operations. The write cost still needs measurement. |
| `product_seller_product_active_idx` | Reject | Made a broad seller report slower by switching to a costly execution plan. |
| `order_month_cover_idx` | Omit | Helps monthly order summaries, but they run infrequently and another date-filtered case becomes slower. |
| `order_item_month_order_cover_idx` | Omit | Removes a large sort, but duplicates a wide item index for an occasional report. |
| `order_date_order_cover_idx` | Omit | Mostly speeds up queries that were already responsive. |
| `order_amount_order_active_idx` | Omit | Makes the highest-order lookup extremely fast, but the subsecond baseline was already adequate. |
| `order_item_order_date_brin_idx` | Optional | Tiny and useful for weekly item reporting, but that workflow is not part of the assumed daily usage. |
| `order_item_order_product_cover_idx` | Reject | No useful index access was demonstrated in the tested cases. |

**Recommendation:** Keep the 25 required PK/UNIQUE indexes and **provisionally recommend only the two optional indexes above**. This is a business-informed choice, **not proof that two is mathematically optimal**.

**Implementation note:** This is a recommendation, not a deployment claim. [`database/indexes.sql`](../database/indexes.sql) still contains the seven-index test definitions; running that file does **not** install only the recommended pair.

## 4. How I measured it

- **Environment:** PostgreSQL 16.15 on an isolated database copy; Intel i7-11800H, approximately 31 GiB RAM.
- **Protocol:** Three warmup runs followed by seven measured executions of each fixed SQL case; report the median.
- **Evidence:** `EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS, FORMAT JSON)` to inspect access paths, actual work, and buffer usage.
- **Fair baseline:** All 25 required indexes were retained; optional reporting indexes were physically absent from the no-optional-index baseline.
- **Correctness:** 27 directly comparable original/rewrite cases passed two-way `EXCEPT ALL` checks. Unmatched cases were not assigned invented baseline timings.

The complete test set contains **37 cases across 12 reporting functions**. The numbers above come from one primary validation round; separate targeted tests help explain individual index behavior without replacing those results.

### Limits of this analysis

- The dataset and reporting frequency are **synthetic assumptions**, not production traffic.
- Timings are for standalone SQL, not application endpoints or dashboard rendering.
- The maintenance impact of optional indexes on **inserts, updates, WAL, and concurrency was not measured**. The dataset implies roughly 117,000 item rows per day on average, but that does not establish actual production insert rates.
- Benchmark timings vary between runs. Small differences should not be treated as proof that an index helped or hurt.
- Some broad reports still need several seconds. If they become frequent or disruptive, caching, scheduled summaries, or pre-aggregation may be more useful than more OLTP indexes.

## 5. Explore the implementation and evidence

- [Original reporting SQL](../database/reporting/original_queries.sql) · [Rewritten reporting SQL](../database/reporting/queries.sql) · [Reporting functions](../database/reporting/functions.sql)
- [Index definitions](../database/indexes.sql) · [Measurement methodology](#4-how-i-measured-it) · [Analysis limits](#limits-of-this-analysis)
- [Repository guidelines and business assumptions](../AGENTS.md)

A separate bulk-loading experiment also showed that **loading first and building indexes afterward** took **456.742 s**, versus **560.001 s** when the tested indexes were maintained during loading. That is a bulk-load result, **not** a measurement of production write overhead.

---

**Takeaway:** Optimize slow SQL first. Add indexes when they solve meaningful problems. Stop when extra performance is no longer worth the cost.
