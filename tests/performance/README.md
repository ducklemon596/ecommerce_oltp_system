# Manual performance tests

Large generation and PostgreSQL loading benchmarks belong here. They are run
explicitly, not through `unittest discover`, so regular CI only runs unit and
integration correctness tests.

Use the loader benchmark command when PostgreSQL and generated part files are
available:

```bash
uv run python -m ecommerce_oltp_system.loader.benchmark_large_tables
```
