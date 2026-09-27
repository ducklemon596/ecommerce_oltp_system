# Manual performance tests

Large generation and PostgreSQL loading benchmarks are intentionally separate
from normal unit and integration tests. `unittest discover` does not run them.

This repository currently records benchmark findings in the [root README](../../README.md), but does not include a runnable benchmark harness. Add a focused, repeatable script here before treating new measurements as comparable to the recorded results.
