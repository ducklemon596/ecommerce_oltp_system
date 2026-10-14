# Manual performance tests

Large generation and PostgreSQL loading benchmarks are intentionally separate
from normal unit and integration tests. `unittest discover` does not run them.

The [reporting catalog](../../database/reporting/README.md) links historical SQL benchmarks
and the runners under `scripts/`. Archived inputs live under `benchmarks/`.
Generated runs reuse configured latest/ directories; historical reports remain protected. Large PostgreSQL
benchmarks are manual; the reporting integration tests use only tiny fixtures and
do not run performance workloads or change source indexes.
