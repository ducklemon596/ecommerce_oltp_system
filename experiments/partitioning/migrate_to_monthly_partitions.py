"""Migrate the loaded transactional tables to January--May 2025 partitions.

EXPERIMENT ONLY: this changes keys and is incompatible with current loader
UPSERT targets. See README.md and rehearse only on an isolated database clone.
The script
holds an exclusive lock and makes the table replacement in one transaction, so
readers see either the original tables or the fully populated partitioned ones.
"""

from __future__ import annotations

from time import perf_counter

import psycopg2

from ecommerce_oltp_system.loader.db.connection import database_config


MONTHS = ("2025_01", "2025_02", "2025_03", "2025_04", "2025_05")
WINDOW_START = "2025-01-01"
WINDOW_END = "2025-06-01"


def partition_ddl(table: str, parent: str) -> str:
    """Return five fixed monthly partitions for a January--May 2025 parent."""
    months = (
        ("2025_01", "2025-01-01", "2025-02-01"),
        ("2025_02", "2025-02-01", "2025-03-01"),
        ("2025_03", "2025-03-01", "2025-04-01"),
        ("2025_04", "2025-04-01", "2025-05-01"),
        ("2025_05", "2025-05-01", "2025-06-01"),
    )
    return "\n".join(
        f"CREATE TABLE {table}_{suffix} PARTITION OF {parent} "
        f"FOR VALUES FROM ('{start}') TO ('{end}');"
        for suffix, start, end in months
    )


def already_partitioned(cursor) -> bool:
    """Return whether the live `order` parent has already been partitioned."""
    cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_partitioned_table WHERE partrelid = '\"order\"'::regclass)")
    return cursor.fetchone()[0]


def validate_source_window(cursor) -> None:
    """Fail before DDL if rows cannot fit the five requested monthly partitions."""
    cursor.execute(
        """
        SELECT
            (SELECT count(*) FROM "order" WHERE order_date < %s OR order_date >= %s),
            (SELECT count(*) FROM order_item WHERE order_date < %s OR order_date >= %s),
            (SELECT count(*) FROM order_item oi JOIN "order" o ON o.order_id = oi.order_id
             WHERE oi.order_date <> o.order_date)
        """,
        (WINDOW_START, WINDOW_END, WINDOW_START, WINDOW_END),
    )
    outside_orders, outside_items, mismatched_dates = cursor.fetchone()
    if outside_orders or outside_items or mismatched_dates:
        raise RuntimeError(
            "Cannot partition: found "
            f"{outside_orders} out-of-window orders, {outside_items} out-of-window items, "
            f"and {mismatched_dates} item/order date mismatches."
        )


def migrate(database) -> None:
    """Build, validate, and atomically swap partitioned transaction tables.

    This is a one-time schema migration for the existing full dataset. It
    copies `order` and `order_item` into replacement range-partitioned parents,
    creates composite PK/unique/FK constraints compatible with partitioning,
    swaps names only after counts match, and drops the old copies before commit.
    It also creates the required partitioned `order_item(product_id)` index.
    """
    started = perf_counter()
    try:
        with database.cursor() as cursor:
            if already_partitioned(cursor):
                cursor.execute("CREATE INDEX IF NOT EXISTS order_item_product_id_idx ON order_item (product_id)")
                database.commit()
                print("SKIPPED table migration: order is already partitioned; ensured product index exists.")
                return

            # The migration is deliberately a maintenance operation: no loader
            # transaction may insert while source data is being copied and swapped.
            cursor.execute('LOCK TABLE "order", order_item IN ACCESS EXCLUSIVE MODE')
            validate_source_window(cursor)

            cursor.execute(
                """
                CREATE TABLE order_partitioned (
                    order_id SERIAL NOT NULL,
                    order_code VARCHAR(20) NOT NULL,
                    customer_id INTEGER NOT NULL REFERENCES customer (customer_id),
                    order_date TIMESTAMP NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    total_amount DECIMAL(12, 2) NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    created_by TEXT NOT NULL,
                    updated_at TIMESTAMP NULL, updated_by TEXT NULL,
                    deleted_at TIMESTAMP NULL, deleted_by TEXT NULL,
                    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT order_partitioned_pkey PRIMARY KEY (order_id, order_date),
                    CONSTRAINT order_partitioned_code_date_unique UNIQUE (order_code, order_date),
                    CONSTRAINT order_partitioned_status_check CHECK (status IN ('PLACED', 'PAID', 'SHIPPED', 'DELIVERED', 'CANCELLED', 'RETURNED')),
                    CONSTRAINT order_partitioned_total_check CHECK (total_amount >= 0),
                    CONSTRAINT order_partitioned_created_check CHECK (created_at >= order_date)
                ) PARTITION BY RANGE (order_date);
                """
            )
            cursor.execute(partition_ddl("order_partitioned", "order_partitioned"))
            cursor.execute('INSERT INTO order_partitioned SELECT * FROM "order"')
            cursor.execute('SELECT count(*) FROM order_partitioned')
            new_order_count = cursor.fetchone()[0]
            cursor.execute('SELECT count(*) FROM "order"')
            if new_order_count != cursor.fetchone()[0]:
                raise RuntimeError("Order copy count does not match source")

            cursor.execute(
                """
                CREATE TABLE order_item_partitioned (
                    order_item_id BIGSERIAL NOT NULL,
                    order_item_code VARCHAR(20) NOT NULL,
                    order_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL REFERENCES product (product_id),
                    order_date TIMESTAMP NOT NULL,
                    quantity INTEGER NOT NULL,
                    unit_price DECIMAL(12, 2) NOT NULL,
                    subtotal DECIMAL(12, 2) NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    created_by TEXT NOT NULL,
                    updated_at TIMESTAMP NULL, updated_by TEXT NULL,
                    deleted_at TIMESTAMP NULL, deleted_by TEXT NULL,
                    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT order_item_partitioned_pkey PRIMARY KEY (order_item_id, order_date),
                    CONSTRAINT order_item_partitioned_code_date_unique UNIQUE (order_item_code, order_date),
                    CONSTRAINT order_item_partitioned_source_unique UNIQUE (order_id, product_id, order_date),
                    CONSTRAINT order_item_partitioned_order_date_fkey FOREIGN KEY (order_id, order_date)
                        REFERENCES order_partitioned (order_id, order_date),
                    CONSTRAINT order_item_partitioned_quantity_check CHECK (quantity > 0),
                    CONSTRAINT order_item_partitioned_price_check CHECK (unit_price > 0),
                    CONSTRAINT order_item_partitioned_subtotal_check CHECK (subtotal = quantity * unit_price),
                    CONSTRAINT order_item_partitioned_created_check CHECK (created_at >= order_date)
                ) PARTITION BY RANGE (order_date);
                """
            )
            cursor.execute(partition_ddl("order_item_partitioned", "order_item_partitioned"))
            cursor.execute('INSERT INTO order_item_partitioned SELECT * FROM order_item')
            cursor.execute('SELECT count(*) FROM order_item_partitioned')
            new_item_count = cursor.fetchone()[0]
            cursor.execute('SELECT count(*) FROM order_item')
            if new_item_count != cursor.fetchone()[0]:
                raise RuntimeError("Order-item copy count does not match source")

            # `order_item` uses a parent partitioned index so each monthly leaf
            # receives the same product lookup index used by the report query.
            cursor.execute('ALTER TABLE order_item RENAME TO order_item_legacy')
            cursor.execute('ALTER TABLE "order" RENAME TO order_legacy')
            cursor.execute('ALTER TABLE order_partitioned RENAME TO "order"')
            cursor.execute('ALTER TABLE order_item_partitioned RENAME TO order_item')
            cursor.execute('CREATE INDEX order_item_product_id_idx ON order_item (product_id)')
            cursor.execute("SELECT setval(pg_get_serial_sequence('\"order\"', 'order_id'), (SELECT max(order_id) FROM \"order\"), true)")
            cursor.execute("SELECT setval(pg_get_serial_sequence('order_item', 'order_item_id'), (SELECT max(order_item_id) FROM order_item), true)")
            cursor.execute('DROP TABLE order_item_legacy')
            cursor.execute('DROP TABLE order_legacy')
            cursor.execute('ANALYZE "order"')
            cursor.execute('ANALYZE order_item')
        database.commit()
        print(f"MIGRATED {new_order_count:,} orders and {new_item_count:,} order items in {perf_counter() - started:.2f}s.")
    except Exception:
        database.rollback()
        raise


def main() -> None:
    """Run the one-time partition migration against `database.ini`."""
    with psycopg2.connect(**database_config('database.ini')) as database:
        migrate(database)


if __name__ == '__main__':
    main()
