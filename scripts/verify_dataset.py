"""Compare source CSV values to PostgreSQL and optionally repair incomplete files.

Run from the repository root with .venv/bin/python scripts/verify_dataset.py.
Only session-local temporary tables are written unless --repair is supplied.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from time import perf_counter

import psycopg2
from psycopg2 import sql

from ecommerce_oltp_system.loader.config import TABLE_LOADS, ORDER_LOAD, ORDER_ITEM_LOAD
from ecommerce_oltp_system.loader.db.connection import database_config
from ecommerce_oltp_system.loader.db.schema import apply_schema
from ecommerce_oltp_system.loader.checkpoint.repository import file_checksum
from ecommerce_oltp_system.loader.pipeline import find_paired_order_part_paths
from ecommerce_oltp_system.loader.strategies.small_table import load_table
from ecommerce_oltp_system.loader.strategies.large_part import load_large_part


def verify_file(database, config, path):
    """COPY into a temporary typed table and compare every source field by code.

    loaded_at is excluded because it is database-managed. Expected positional
    parent IDs and order IDs are checked separately from source attributes.
    """
    started = perf_counter()
    columns = tuple(config.csv_columns if hasattr(config, 'csv_columns') else config.columns)
    fields = sql.SQL(', ').join(map(sql.Identifier, columns))
    with database.cursor() as cursor:
        cursor.execute(sql.SQL('CREATE TEMP TABLE audit_source ON COMMIT DROP AS SELECT {} FROM {} WITH NO DATA').format(fields, sql.Identifier(config.table)))
        cursor.execute('ALTER TABLE audit_source ADD COLUMN audit_position BIGINT GENERATED ALWAYS AS IDENTITY')
        with path.open(encoding='utf-8', newline='') as source:
            import csv
            header = next(csv.reader(source))
            if header != list(columns):
                raise ValueError(f'Unexpected header: {path}')
            source.seek(0)
            cursor.copy_expert(sql.SQL("COPY audit_source ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE, NULL '')").format(fields).as_string(database), source)
        cursor.execute('ANALYZE audit_source')
        key = config.conflict_columns[0]
        compared = [column for column in columns if column != 'loaded_at']
        source_row = sql.SQL(', ').join(sql.SQL('s.{}').format(sql.Identifier(column)) for column in compared)
        target_row = sql.SQL(', ').join(sql.SQL('t.{}').format(sql.Identifier(column)) for column in compared)
        position_check = sql.SQL('FALSE')
        if getattr(config, 'requires_positional_ids', False):
            position_check = sql.SQL('t.{} <> s.audit_position').format(sql.Identifier(config.primary_key))
        elif config.table == 'order':
            position_check = sql.SQL("t.order_id <> substring(s.order_code FROM 5)::bigint")
        cursor.execute(sql.SQL('''SELECT count(*),
            count(*) FILTER (WHERE t.{pk} IS NULL),
            count(*) FILTER (WHERE t.{pk} IS NOT NULL AND ROW({source}) IS DISTINCT FROM ROW({target})),
            count(*) FILTER (WHERE {position}),
            count(*) - count(DISTINCT s.{key})
            FROM audit_source s LEFT JOIN {table} t ON s.{key} = t.{key}''').format(
                pk=sql.Identifier(config.primary_key), source=source_row, target=target_row,
                position=position_check, key=sql.Identifier(key), table=sql.Identifier(config.table)))
        rows, missing, changed, wrong_ids, duplicates = cursor.fetchone()
    database.commit()
    result = dict(table=config.table, file=str(path), rows=rows, missing=missing,
                  changed=changed, wrong_ids=wrong_ids, duplicate_source_keys=duplicates,
                  sha256=file_checksum(path), elapsed_seconds=round(perf_counter()-started, 3))
    print(json.dumps(result), flush=True)
    return result


def main():
    """Verify all files in dependency order; repair only files with missing/changed rows."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repair', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('reports/data_validation/latest'))
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    database = psycopg2.connect(**database_config('database.ini'))
    pairs = [(config, Path('data') / f'{config.table}.csv') for config in TABLE_LOADS]
    orders, items = find_paired_order_part_paths(Path('data'))
    for order, item in zip(orders, items):
        pairs.extend([(ORDER_LOAD, order), (ORDER_ITEM_LOAD, item)])
    results = []
    totals = defaultdict(int)
    schema_applied = False
    for config, path in pairs:
        result = verify_file(database, config, path)
        if result['duplicate_source_keys'] or result['wrong_ids']:
            raise RuntimeError(f'Unsafe positional IDs or duplicate source keys: {path}')
        if args.repair and (result['missing'] or result['changed']):
            if not schema_applied:
                apply_schema(database)
                schema_applied = True
            loader = load_table if hasattr(config, 'csv_columns') else load_large_part
            loader(database, config, path)
            result = verify_file(database, config, path)
            result['repaired'] = True
        results.append(result)
        totals[config.table] += result['rows']
        (output / 'data_verification.json').write_text(json.dumps(results, indent=2) + '\n')
    counts = {}
    with database.cursor() as cursor:
        for table, expected in totals.items():
            cursor.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table)))
            counts[table] = dict(csv_rows=expected, database_rows=cursor.fetchone()[0])
    database.close()
    (output / 'table_counts.json').write_text(json.dumps(counts, indent=2) + '\n')
    if any(row['missing'] or row['changed'] for row in results):
        raise RuntimeError('Source rows remain missing or different; see data_verification.json')
    print('VERIFIED all source rows and positional IDs; table counts:', counts, flush=True)


if __name__ == '__main__':
    main()
