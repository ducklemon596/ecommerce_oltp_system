"""Load fixed SQL workloads and result locations without database side effects.

The benchmark runners, snapshot script, and correctness tests share these named
SQL blocks. JSON configuration keeps the benchmark dependency set unchanged.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "benchmarks/cases.json").read_text(encoding="utf-8"))


def read_sql_blocks(path: Path) -> dict[str, str]:
    """Read SQL keyed by '-- benchmark-query: ID', preserving measured bodies."""
    source = path.read_text(encoding="utf-8")
    markers = list(re.finditer(r"^-- benchmark-query: (\w+)\s*$", source, flags=re.MULTILINE))
    blocks = {}
    for index, marker in enumerate(markers):
        name = marker.group(1)
        if name in blocks:
            raise ValueError(f"Duplicate SQL case {name!r} in {path}")
        end = markers[index + 1].start() if index + 1 < len(markers) else len(source)
        blocks[name] = source[marker.end():end].strip().rstrip(";")
        if not blocks[name]:
            raise ValueError(f"Empty SQL case {name!r} in {path}")
    if not blocks:
        raise ValueError(f"No named SQL cases in {path}")
    return blocks


def load_query_versions() -> dict[str, tuple[str, str]]:
    """Return each fixed analytical case's original and rewritten SQL.

    Cases without an actual rewrite reuse the original statement; there is no
    duplicate copy of the first four unchanged queries in the optimized archive.
    """
    config = CASES["analytical"]
    original = read_sql_blocks(ROOT / config["original_sql"])
    optimized = read_sql_blocks(ROOT / config["optimized_sql"])
    ids = [case["id"] for case in config["cases"]]
    if set(original) != set(ids) or not set(optimized).issubset(original):
        raise ValueError("Archived SQL case IDs do not match benchmarks/cases.json")
    return {name: (original[name], optimized.get(name, original[name])) for name in ids}


def load_example_queries() -> dict[str, str]:
    """Return the eight analytical examples from the shared 13-requirement file."""
    examples = read_sql_blocks(ROOT / CASES["examples"])
    return {case["id"]: examples[case["id"]] for case in CASES["analytical"]["cases"]}


def read_measurements(path: Path) -> list[dict[str, str]]:
    """Read standard or visually padded historical CSV without changing its bytes.

    Some saved measurements have whitespace around column names and before
    quoted JSON cells. Normalize padding so report regeneration retains metrics
    and correctly parses quoted cells containing commas.
    """
    with path.open(encoding="utf-8", newline="") as source:
        return [
            {key.strip(): value.strip() for key, value in row.items()}
            for row in csv.DictReader(source, skipinitialspace=True)
        ]


def validate_output_directory(output: Path, overwrite: bool = False) -> None:
    """Protect frozen historical evidence; stable latest/ directories are reusable."""
    protected = {(ROOT / directory).resolve() for directory in CASES["historical_output_directories"]}
    if output.resolve() in protected and output.exists() and not overwrite:
        raise ValueError("Historical results already exist; use the stable latest/ output or explicitly pass --overwrite.")
