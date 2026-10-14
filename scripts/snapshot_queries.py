"""Save complete query results, EXPLAIN ANALYZE plans, and measured timings.

Run from the repository root. SQL calls are read from database/reporting/examples.sql;
artifacts default to reports/sql_optimization/latest_snapshot. Does not change schema, indexes, or source data.
"""

import argparse
import csv
import json
import os
from pathlib import Path
from time import perf_counter

import psycopg2

from ecommerce_oltp_system.loader.db.connection import database_config

if __package__:
    from .reporting_workloads import CASES, ROOT, load_example_queries, validate_output_directory
else:
    from reporting_workloads import CASES, ROOT, load_example_queries, validate_output_directory


def write_report(output, summaries, metadata, verification_dir, label):
    """Produce a readable report with timings, verification, and result previews."""
    catalog_link = Path(os.path.relpath(Path('database/reporting/README.md').resolve(), output.resolve())).as_posix()
    lines = [
        f'# SQL query snapshot: {label}', '',
        f"Captured at: {metadata['captured_at']}", '',
        f"Database: `{metadata['database']}`. Server: {metadata['version']}", '',
        f'See [report definitions and measurement method]({catalog_link}).', '',
        'Revenue includes all statuses and excludes soft-deleted rows. Seller',
        'revenue is attributed from item subtotals. These are single executions',
        'with the indexes and cache state recorded in `environment.json`.', '',
        '## Data verification', '',
    ]
    counts = json.loads((verification_dir / 'table_counts.json').read_text())
    audit = json.loads((verification_dir / 'data_verification.json').read_text())
    lines += [f"Compared all {len(audit)} CSV files by business key and every source", 
              'attribute except database-managed `loaded_at`. Verified positional',
              'IDs and source key uniqueness. SHA-256 digests are saved per file.', '',
              '| Table | Source CSV rows | Database rows |', '|---|---:|---:|']
    for table, count in counts.items():
        lines.append(f"| {table} | {count['csv_rows']:,} | {count['database_rows']:,} |")
    failures = sum(row['missing'] + row['changed'] + row['wrong_ids'] + row['duplicate_source_keys'] for row in audit)
    repaired = sum(bool(row.get('repaired')) for row in audit)
    load_message = (f'Repaired and reverified {repaired} source files.' if repaired else
                    'The existing dataset was already loaded; no data reload was necessary.')
    lines += ['', f'Missing/different rows or invalid source IDs/keys: **{failures:,}**.', '',
              load_message, '',
              'Verification does not create checkpoints for historical loads.', '',
              '## Runtime comparison', '',
              '| Query | Result rows | Planning ms | Execution ms | Export seconds |',
              '|---|---:|---:|---:|---:|']
    for row in summaries:
        name = row['query']
        query_path = ROOT / CASES['examples']
        source_link = Path(os.path.relpath(query_path.resolve(), output.resolve())).as_posix()
        lines.append(f"| [{name}]({source_link}) | {row['result_rows']:,} | {row['planning_ms']:.3f} | {row['execution_ms']:.3f} | {row['export_wall_seconds']:.3f} |")
    lines += ['', 'Execution ms is server time from EXPLAIN ANALYZE. Export seconds',
              'measures the second execution plus network fetch and CSV writing.', '',
              '## Result snapshots', '']
    for row in summaries:
        name = row['query']
        query_path = ROOT / CASES['examples']
        source_link = Path(os.path.relpath(query_path.resolve(), output.resolve())).as_posix()
        lines += [f'### {name}', '',
                  f'[SQL]({source_link}) · [Complete CSV](raw/{name}.csv) · [Readable plan](raw/{name}.plan.txt) · [Full plan with buffers](raw/{name}.plan.json)', '',
                  f"Showing {len(row['preview'])} of {row['result_rows']:,} result rows.", '',
                  '| ' + ' | '.join(row['headers']) + ' |',
                  '| ' + ' | '.join('---' for _ in row['headers']) + ' |']
        for values in row['preview']:
            lines.append('| ' + ' | '.join(value.replace('|', '\\|').replace('\n', ' ') for value in values) + ' |')
        lines.append('')
    (output / 'README.md').write_text('\n'.join(lines) + '\n')


def main():
    """Measure each query once with EXPLAIN, then stream a complete CSV snapshot."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('reports/sql_optimization/latest_snapshot'),
                        help='Directory for plans, timings, and result CSVs.')
    parser.add_argument('--label', default='canonical functions',
                        help='Short description used in the generated report heading.')
    parser.add_argument('--overwrite', action='store_true', help='Explicitly replace existing snapshots.')
    parser.add_argument('--verification-dir', type=Path, default=Path('reports/data_validation/latest'), help='Saved source audit produced by verify_dataset.py.')
    args = parser.parse_args()
    output = args.output
    try:
        validate_output_directory(output, args.overwrite)
    except ValueError as error:
        parser.error(str(error))
    output.mkdir(parents=True, exist_ok=True)
    raw = output / 'raw'
    raw.mkdir(parents=True, exist_ok=True)
    if not all((args.verification_dir / name).exists() for name in ('table_counts.json', 'data_verification.json')):
        parser.error('Run verify_dataset.py first or supply --verification-dir with a completed source audit.')
    database = psycopg2.connect(**database_config('database.ini'))
    database.set_session(readonly=True, isolation_level='REPEATABLE READ')
    with database.cursor() as cursor:
        cursor.execute('SELECT version(), current_database(), current_timestamp')
        version, db_name, captured_at = cursor.fetchone()
        cursor.execute("SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = current_schema() ORDER BY tablename, indexname")
        indexes = cursor.fetchall()
        cursor.execute("SELECT name, setting, unit FROM pg_settings WHERE name IN ('shared_buffers','work_mem','max_parallel_workers_per_gather','jit','effective_cache_size') ORDER BY name")
        settings = cursor.fetchall()
    metadata = dict(version=version, database=db_name, captured_at=captured_at.isoformat(),
                    indexes=indexes, settings=settings,
                    method='One EXPLAIN ANALYZE followed by one complete result export per query; no cache reset. All queries share a read-only repeatable-read snapshot.')
    (output / 'environment.json').write_text(json.dumps(metadata, indent=2) + '\n')
    summaries = []
    for index, (name, query) in enumerate(load_example_queries().items()):
        started = perf_counter()
        with database.cursor() as cursor:
            cursor.execute('EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS, FORMAT JSON) ' + query)
            plan = cursor.fetchone()[0]
        explain_elapsed = perf_counter() - started
        (raw / f'{name}.plan.json').write_text(json.dumps(plan, indent=2) + '\n')
        # Derive readable plan from the same execution, without measuring twice.
        def plan_lines(node, depth=0):
            label = node['Node Type']
            if 'Relation Name' in node:
                label += ' on ' + node['Relation Name']
            lines = [f"{'  '*depth}{label}: actual {node.get('Actual Startup Time', 0):.3f}..{node.get('Actual Total Time', 0):.3f} ms, rows={node.get('Actual Rows')}, loops={node.get('Actual Loops')}"]
            for child in node.get('Plans', []):
                lines.extend(plan_lines(child, depth+1))
            return lines
        (raw / f'{name}.plan.txt').write_text('\n'.join(plan_lines(plan[0]['Plan'])) + f"\nPlanning time: {plan[0]['Planning Time']} ms\nExecution time: {plan[0]['Execution Time']} ms\nFull details and buffer counts: {name}.plan.json\n")
        started = perf_counter()
        count = 0
        preview = []
        with database.cursor(name=f'report_{index}') as cursor:
            cursor.itersize = 10000
            cursor.execute(query)
            first = cursor.fetchmany(10000)
            headers = [column.name for column in cursor.description]
            with (raw / f'{name}.csv').open('w', newline='', encoding='utf-8') as target:
                writer = csv.writer(target)
                writer.writerow(headers)
                writer.writerows(first)
                count += len(first)
                preview = [list(map(str, row)) for row in first[:5]]
                for row in cursor:
                    writer.writerow(row)
                    count += 1
        result = dict(query=name, result_rows=count,
                      planning_ms=plan[0]['Planning Time'], execution_ms=plan[0]['Execution Time'],
                      explain_wall_seconds=round(explain_elapsed, 3),
                      export_wall_seconds=round(perf_counter()-started, 3),
                      headers=headers, preview=preview)
        summaries.append(result)
        (output / 'query_summary.json').write_text(json.dumps(summaries, indent=2) + '\n')
        print(json.dumps(result), flush=True)
    database.rollback()
    database.close()
    write_report(output, summaries, metadata, args.verification_dir, args.label)


if __name__ == '__main__':
    main()
