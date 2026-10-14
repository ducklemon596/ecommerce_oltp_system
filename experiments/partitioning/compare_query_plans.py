"""Write a structural before/after comparison from two query snapshot folders."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


def result_digest(path: Path) -> str:
    """Return a stable SHA-256 digest for one exported query-result CSV."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plan_lines(node: dict, depth: int = 0) -> list[str]:
    """Render a compact detailed node tree from PostgreSQL's JSON EXPLAIN plan."""
    identity = node['Node Type']
    if node.get('Relation Name'):
        identity += f" on {node['Relation Name']}"
    if node.get('Index Name'):
        identity += f" using {node['Index Name']}"
    details = []
    for key in ('Index Cond', 'Hash Cond', 'Merge Cond', 'Join Filter', 'Filter'):
        if node.get(key):
            details.append(f"{key}: {node[key]}")
    buffer = node.get('Shared Hit Blocks', 0), node.get('Shared Read Blocks', 0)
    suffix = f"actual={node.get('Actual Total Time', 0):.3f}ms rows={node.get('Actual Rows')} loops={node.get('Actual Loops')} buffers(hit/read)={buffer[0]}/{buffer[1]}"
    if details:
        suffix += ' | ' + '; '.join(details)
    lines = [f"{'  ' * depth}{identity} — {suffix}"]
    for child in node.get('Plans', []):
        lines.extend(plan_lines(child, depth + 1))
    return lines


def main() -> None:
    """Compare baseline and partitioned report output, including exact CSV results."""
    before = Path('reports/sql_optimization/raw/baseline')
    after = Path('experiments/partitioning/results')
    output = after / 'PLAN_COMPARISON.md'
    before_summary = {row['query']: row for row in json.loads(Path('reports/sql_optimization/baseline/query_summary.json').read_text())}
    after_summary = {row['query']: row for row in json.loads((after / 'query_summary.json').read_text())}
    names = sorted(before_summary)
    lines = [
        '# Partitioning and product-index plan comparison', '',
        'Each snapshot executed `EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS, FORMAT JSON)` once and then reran the query to export results. Timings are single-run observations; cache state was not reset.', '',
        '| Query | Results unchanged | Before execution ms | After execution ms | Change |',
        '|---|---|---:|---:|---:|',
    ]
    for name in names:
        old, new = before_summary[name], after_summary[name]
        same = result_digest(before / f'{name}.csv') == result_digest(after / 'raw' / f'{name}.csv')
        change = (new['execution_ms'] / old['execution_ms'] - 1) * 100
        lines.append(f"| {name} | {'yes' if same else '**NO**'} | {old['execution_ms']:.3f} | {new['execution_ms']:.3f} | {change:+.1f}% |")
    lines += ['', '## Detailed plan trees', '']
    for name in names:
        old_plan = json.loads((before / f'{name}.plan.json').read_text())[0]
        new_plan = json.loads((after / 'raw' / f'{name}.plan.json').read_text())[0]
        lines += [f'### {name}', '', '<details><summary>Before partitioning</summary>', '', '```text', *plan_lines(old_plan['Plan']), '```', '', '</details>', '', '<details><summary>After partitioning and product index</summary>', '', '```text', *plan_lines(new_plan['Plan']), '```', '', '</details>', '']
    output.write_text('\n'.join(lines) + '\n')
    print(f'Wrote {output}')


if __name__ == '__main__':
    main()
