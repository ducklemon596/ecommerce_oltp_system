# Reporting and performance evidence

- [SQL optimization](sql_optimization/README.md): the primary eight-query,
  three-stage performance report, read/write trade-offs and index decisions.
- [Dynamic reports](dynamic_reports/README.md): complementary five-function
  historical comparison, including the top-brand rewrite regression.
- [Source-data validation](data_validation/): original file checksums, value/ID
  comparisons and table counts.
- [Function catalog](../database/reporting/README.md): the current reporting
  API, 13-requirement mapping, examples and consolidated workload analysis.

Controlled medians and original single-run baseline metadata remain distinct.
Original execution times/metadata were moved without alteration; see the
[cleanup inventory](../docs/repository_cleanup.md) and its provenance manifest.
Full raw plans/result exports are available locally under ignored raw/ folders.

Future runs replace stable latest/ directories and leave the committed historical
reports intact. Reproduction commands and input versions are described in
[benchmarks/README.md](../benchmarks/README.md).
