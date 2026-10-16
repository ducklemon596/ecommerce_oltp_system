"""Current SQL/functions and business contracts in a rolled-back fixture schema.

No production functions, records, indexes, or constraints are modified.
"""

from __future__ import annotations

import re
import unittest
import uuid
from pathlib import Path

import psycopg2
from psycopg2 import sql

from ecommerce_oltp_system.loader.db.connection import database_config
from ecommerce_oltp_system.reporting import REPORTS, execute_report
from tests.reporting_support import example_parameters, function_definitions, standalone_queries


ROOT = Path(__file__).resolve().parents[2]
WINDOW = ("2025-01-01", "2025-06-01")


class ReportingIntegrationTests(unittest.TestCase):
    """Verify one reporting contract per test against adversarial, valid DB data."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create the fixture schema without committing any DDL or records."""
        try:
            cls.database = psycopg2.connect(**database_config(ROOT / "database.ini"))
        except (psycopg2.OperationalError, FileNotFoundError) as error:
            raise unittest.SkipTest(f"PostgreSQL unavailable: {error}") from error
        try:
            with cls.database.cursor() as cursor:
                schema = sql.Identifier(f"report_test_{uuid.uuid4().hex[:12]}")
                cursor.execute(sql.SQL("CREATE SCHEMA {}").format(schema))
                cursor.execute(sql.SQL("SET LOCAL search_path TO {}").format(schema))
                cursor.execute((ROOT / "database/schema.sql").read_text())
                cursor.execute((ROOT / "database/reporting/functions.sql").read_text())
                cls._seed(cursor)
        except BaseException:
            cls.database.rollback()
            cls.database.close()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        """Rollback removes the entire temporary schema, functions, and fixtures."""
        cls.database.rollback()
        cls.database.close()

    @staticmethod
    def _seed(cursor) -> None:
        """Seed boundary dates, deletion scopes, multi-seller orders, and rank ties."""
        cursor.executemany(
            "INSERT INTO brand (brand_id,brand_code,brand_name,country,created_at,created_by,is_deleted) "
            "VALUES (%s,%s,%s,'VN','2024-12-01','test',%s)",
            [(1, "B1", "One", False), (2, "B2", "Two", False), (3, "B3", "Deleted", True)],
        )
        cursor.executemany(
            "INSERT INTO category (category_id,category_code,category_name,level,created_at,created_by,is_deleted) "
            "VALUES (%s,%s,%s,1,'2024-12-01','test',%s)",
            [(1, "C1", "One", False), (2, "C2", "Two", False), (3, "C3", "Deleted", True)],
        )
        cursor.executemany(
            "INSERT INTO seller (seller_id,seller_code,seller_name,join_date,created_at,created_by,seller_type,rating,country,is_deleted) "
            "VALUES (%s,%s,%s,'2024-12-01','2024-12-01','test','Official',4,'Vietnam',%s)",
            [(1, "S1", "One", False), (2, "S2", "Two", False), (3, "S3", "Deleted", True)],
        )
        cursor.execute(
            "INSERT INTO customer (customer_id,customer_code,customer_name,email,phone,gender,address,city,created_at,created_by) "
            "VALUES (1,'C1','Customer','test@example.com','0123456789','Male','Address','City','2025-01-01','test')"
        )
        cursor.executemany(
            "INSERT INTO product (product_id,product_code,product_name,category_id,brand_id,seller_id,price,stock_qty,rating,created_at,is_active,created_by,is_deleted) "
            "VALUES (%s,%s,%s,%s,%s,%s,10,0,4,'2024-12-01',TRUE,'test',%s)",
            [(i, f"P{i}", f"Product {i}", cat, brand, seller, deleted)
             for i, cat, brand, seller, deleted in [
                 (1, 1, 1, 1, False), (2, 2, 1, 2, False), (3, 1, 2, 1, False),
                 (4, 1, 1, 1, True), (5, 3, 2, 3, False), (6, 2, 3, 2, False), (7, 1, 1, 1, False),
             ]],
        )
        cursor.executemany(
            'INSERT INTO "order" (order_id,order_code,customer_id,order_date,status,total_amount,created_at,created_by,is_deleted) '
            "VALUES (%s,%s,1,%s,%s,%s,'2025-07-01','test',%s)",
            [(i, f"O{i}", date, status, amount, deleted)
             for i, date, status, amount, deleted in [
                 (1, "2025-01-15", "PAID", 50, False), (2, "2025-01-16", "CANCELLED", 60, False),
                 (3, "2025-02-15", "SHIPPED", 40, False), (4, "2025-03-10", "DELIVERED", 90, False),
                 (5, "2025-03-31 23:59:59", "PAID", 20, False), (6, "2025-04-01", "PAID", 50, False),
                 (7, "2025-03-20", "RETURNED", 100, True), (8, "2025-03-22", "PLACED", 0, False),
                 (9, "2025-06-01", "PAID", 30, False), (10, "2025-03-12", "CANCELLED", 90, False),
                 (11, "2025-02-20", "PAID", 60, False), (12, "2025-04-15", "PAID", 10, False),
             ]],
        )
        lines = [
            (1, 1, 2, 10, "2025-01-15", False), (1, 2, 1, 30, "2025-01-15", False),
            (2, 1, 3, 10, "2025-01-16", False), (2, 3, 3, 10, "2025-01-16", False),
            (3, 3, 2, 10, "2025-02-15", False), (3, 4, 2, 10, "2025-02-15", False),
            (4, 1, 2, 10, "2025-03-10", False), (4, 2, 1, 30, "2025-03-10", True),
            (4, 5, 1, 40, "2025-03-10", False), (5, 7, 2, 10, "2025-03-31 23:59:59", False),
            (6, 6, 1, 50, "2025-03-31", False),  # Valid schema, deliberately different order/item dates.
            (7, 1, 10, 10, "2025-03-20", False), (9, 1, 3, 10, "2025-06-01", False),
            (10, 3, 9, 10, "2025-03-12", False), (11, 7, 5, 12, "2025-02-20", False),
            (12, 1, 1, 10, "2025-04-15", True),
        ]
        cursor.executemany(
            "INSERT INTO order_item (order_item_code,order_id,product_id,quantity,unit_price,subtotal,order_date,created_at,created_by,is_deleted) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,'2025-07-01','test',%s)",
            [(f"I{i}", order, product, qty, price, qty * price, date, deleted)
             for i, (order, product, qty, price, date, deleted) in enumerate(lines, 1)],
        )

    def _call(self, name: str, arguments: tuple) -> str:
        """Quote fixture parameters using psycopg2, keeping query comparisons readable."""
        with self.database.cursor() as cursor:
            return cursor.mogrify(
                f"SELECT * FROM {name}({','.join(['%s'] * len(arguments))})", arguments,
            ).decode()

    def _rows(self, query: str) -> list[tuple]:
        """Fetch a small deterministic fixture result."""
        with self.database.cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchall()

    def _assert_equivalent(self, actual: str, expected: str) -> None:
        """Compare result bags in both directions so duplicate-count errors are visible."""
        rows = self._rows(f"""
            WITH actual AS ({actual.rstrip(';')}), expected AS ({expected.rstrip(';')}),
            differences AS (
                (SELECT * FROM actual EXCEPT ALL SELECT * FROM expected)
                UNION ALL (SELECT * FROM expected EXCEPT ALL SELECT * FROM actual)
            ) SELECT count(*) FROM differences
        """)
        self.assertEqual(rows, [(0,)])

    def test_existing_return_columns_remain_compatible(self) -> None:
        """Preserve the five existing callers' column contracts."""
        expected_columns = {
            "report_monthly_revenue": "month total_orders total_quantity total_revenue",
            "report_daily_revenue": "date total_orders total_quantity total_revenue",
            "report_seller_performance": "seller_id seller_name total_orders total_quantity total_revenue",
            "report_top_products_per_brand": "brand_id brand_name product_id product_name total_quantity total_revenue",
            "report_order_status_summary": "status total_orders total_revenue",
        }
        for name, columns in expected_columns.items():
            with self.subTest(function=name), self.database.cursor() as cursor:
                call = self._call(name, WINDOW)
                cursor.execute(f"SELECT * FROM ({call}) r LIMIT 0")
                self.assertEqual([column.name for column in cursor.description], columns.split())

    def test_empty_arrays_match_no_rows(self) -> None:
        """Every optional list filter distinguishes an empty list from NULL."""
        cases = {
            "report_daily_revenue": [([],)],
            "report_seller_performance": [([], None), (None, [])],
            "report_top_products_per_brand": [([], 3)],
            "report_order_status_summary": [([], None), (None, [])],
            "report_orders_by_seller": [([],)],
            "report_items_by_product": [([],)],
            "report_seller_sales": [([],)],
            "report_product_monthly_revenue": [([],)],
        }
        for name, arguments in cases.items():
            for extra in arguments:
                with self.subTest(function=name, arguments=extra):
                    self.assertEqual(self._rows(self._call(name, WINDOW + extra)), [])

    def _assert_optional_list_filters(self, function: str, reference: str) -> None:
        """Compare one function with a reference over the shared filter scenarios."""
        for ids in (None, [], [1], [1, 2], [999]):
            with self.subTest(ids=ids), self.database.cursor() as cursor:
                expected = cursor.mogrify(reference, (WINDOW[0], WINDOW[1], ids, ids)).decode()
                self._assert_equivalent(self._call(function, WINDOW + (ids,)), expected)

    def test_seller_sales_optional_filters_select_seller_groups(self) -> None:
        """Filtering sellers retains exactly their unfiltered aggregate metrics."""
        rows = self._rows(self._call("report_seller_sales", WINDOW))
        for ids in (None, [], [1], [1, 2], [999]):
            with self.subTest(ids=ids):
                expected = [row for row in rows if ids is None or row[0] in ids]
                self.assertEqual(self._rows(self._call("report_seller_sales", WINDOW + (ids,))), expected)

    def test_product_month_optional_filters_select_product_groups(self) -> None:
        """Filtering products leaves their order-month grouping and revenue intact."""
        rows = self._rows(self._call("report_product_monthly_revenue", WINDOW))
        for ids in (None, [], [1], [1, 2], [999]):
            with self.subTest(ids=ids):
                expected = [row for row in rows if ids is None or row[1] in ids]
                self.assertEqual(self._rows(self._call("report_product_monthly_revenue", WINDOW + (ids,))), expected)

    def test_item_export_optional_filters_preserve_deletion_scope(self) -> None:
        """All product-array shapes select only items, with no dimension deletion test."""
        reference = """SELECT order_item_id,order_item_code,order_id,product_id,order_date,
            quantity,unit_price,subtotal FROM order_item
            WHERE order_date >= %s::timestamp AND order_date < %s::timestamp
              AND (%s::integer[] IS NULL OR product_id=ANY(%s::integer[])) AND NOT is_deleted"""
        self._assert_optional_list_filters("report_items_by_product", reference)

    def test_order_list_optional_filters_match_distinct_join(self) -> None:
        """The EXISTS implementation matches an independent distinct outer-join query."""
        reference = """SELECT DISTINCT o.order_id,o.order_code,o.customer_id,o.order_date,o.status,o.total_amount
            FROM "order" o
            LEFT JOIN order_item oi ON oi.order_id=o.order_id AND NOT oi.is_deleted
            LEFT JOIN product p ON p.product_id=oi.product_id AND NOT p.is_deleted
            WHERE o.order_date >= %s::timestamp AND o.order_date < %s::timestamp
              AND (%s::integer[] IS NULL OR p.seller_id=ANY(%s::integer[])) AND NOT o.is_deleted"""
        self._assert_optional_list_filters("report_orders_by_seller", reference)

    def test_null_dates_match_no_rows(self) -> None:
        """Retain existing NULL date behavior across the consolidated catalog."""
        names = re.findall(r"CREATE OR REPLACE FUNCTION (report_\w+)", (ROOT / "database/reporting/functions.sql").read_text())
        for name in names:
            with self.subTest(function=name):
                self.assertEqual(self._rows(self._call(name, (None, WINDOW[1]))), [])

    def test_top_brand_checks_brand_deletion_but_not_seller_deletion(self) -> None:
        """Retain the specific dimension visibility rules of the within-brand report."""
        rows = self._rows(self._call("report_top_products_per_brand", WINDOW + (None, 10)))
        products = {row[2] for row in rows}
        self.assertIn(5, products)  # Seller deleted; brand and product still active.
        self.assertNotIn(6, products)  # Brand deleted.
        self.assertNotIn(4, products)  # Product deleted.

    def test_topn_nonpositive_or_null_returns_no_rows(self) -> None:
        """Keep the common Top-N boundary contract across global and within-brand ranks."""
        for n in (0, -1, None):
            for name in ("report_top_products", "report_highest_value_orders", "report_top_products_per_brand"):
                with self.subTest(function=name, top_n=n):
                    extra = (None, n) if name.endswith("per_brand") else (n,)
                    self.assertEqual(self._rows(self._call(name, WINDOW + extra)), [])

    def test_global_top_products_ties_use_product_id(self) -> None:
        """Global quantity ties ignore revenue and prefer lower product IDs."""
        rows = self._rows(self._call("report_top_products", WINDOW + (3,)))
        self.assertEqual([row[0] for row in rows], [3, 1, 7])

    def test_brand_ranking_ties_use_revenue(self) -> None:
        """Within a brand, equal units rank by revenue before product ID."""
        rows = self._rows(self._call("report_top_products_per_brand", WINDOW + (None, 2)))
        self.assertEqual([row[2] for row in rows if row[0] == 1], [7, 1])

    def test_highest_order_ties_use_order_id(self) -> None:
        """Highest-value ties prefer the lower order ID and exclude deleted orders."""
        rows = self._rows(self._call("report_highest_value_orders", WINDOW + (2,)))
        self.assertEqual([row[0] for row in rows], [4, 10])

    def test_seller_revenue_only_attributes_matching_items(self) -> None:
        """A multi-seller order contributes only the seller's item subtotals."""
        rows = self._rows(self._call("report_seller_sales", ("2025-01-15", "2025-01-16", None)))
        self.assertEqual({row[0]: (row[4], row[7]) for row in rows}, {1: (1, 20), 2: (1, 30)})

    def test_status_counts_multi_seller_order_once(self) -> None:
        """Matching several lines/sellers does not multiply full order totals."""
        rows = self._rows(self._call("report_order_status_summary", ("2025-01-15", "2025-01-16", [1, 2], None)))
        self.assertEqual(rows, [("PAID", 1, 50)])

    def test_status_filters_must_match_the_same_line(self) -> None:
        """Seller/category matches on different lines must not qualify an order."""
        rows = self._rows(self._call("report_order_status_summary", ("2025-01-15", "2025-01-16", [1], [2])))
        self.assertEqual(rows, [])

    def test_order_revenue_does_not_remove_deleted_item_amount(self) -> None:
        """Order revenue and active-line revenue remain intentionally different."""
        order = self._rows(self._call("report_monthly_order_revenue", ("2025-03-10", "2025-03-11")))
        items = self._rows(self._call("report_monthly_revenue", ("2025-03-10", "2025-03-11")))
        self.assertEqual((order[0][-1], items[0][-1]), (90, 60))

    def test_null_seller_filter_includes_orders_without_items(self) -> None:
        """A disabled seller filter includes an active empty order."""
        rows = self._rows(self._call("report_orders_by_seller", ("2025-03-22", "2025-03-23", None)))
        self.assertEqual([row[0] for row in rows], [8])

    def test_item_export_does_not_filter_deleted_parent_or_product(self) -> None:
        """Keep the item export's deliberately narrower soft-deletion scope."""
        rows = self._rows(self._call("report_items_by_product", WINDOW + ([1, 4],)))
        self.assertIn((3, 4), [(row[2], row[3]) for row in rows])
        self.assertIn((7, 1), [(row[2], row[3]) for row in rows])
        self.assertNotIn((12, 1), [(row[2], row[3]) for row in rows])

    def test_daily_revenue_uses_item_timestamp(self) -> None:
        """Preserve the existing function behavior when denormalized dates differ."""
        rows = self._rows(self._call("report_daily_revenue", ("2025-03-01", "2025-04-01", [6])))
        self.assertEqual([(str(row[0]), row[-1]) for row in rows], [("2025-03-31", 50)])

    def test_product_month_uses_order_timestamp(self) -> None:
        """The original product/month requirement groups by its parent order's date."""
        rows = self._rows(self._call("report_product_monthly_revenue", WINDOW + ([6],)))
        self.assertEqual([(str(row[0]), row[-1]) for row in rows], [("2025-04-01", 50)])

    def test_date_window_is_half_open(self) -> None:
        """Include the last March instant and exclude the exact April boundary."""
        rows = self._rows(self._call("report_orders_by_seller", ("2025-03-31", "2025-04-01", None)))
        self.assertEqual([row[0] for row in rows], [5])

    def test_foreign_key_rejects_orphan_items(self) -> None:
        """Verify the schema invariant required by deleted-parent anti-join rewrites."""
        with self.database.cursor() as cursor:
            cursor.execute("SAVEPOINT orphan_test")
            try:
                with self.assertRaises(psycopg2.errors.ForeignKeyViolation):
                    cursor.execute(
                        "INSERT INTO order_item (order_item_code,order_id,product_id,order_date,quantity,unit_price,subtotal,created_at,created_by) "
                        "VALUES ('ORPHAN',999,1,'2025-01-01',1,10,10,'2025-01-01','test')"
                    )
            finally:
                cursor.execute("ROLLBACK TO SAVEPOINT orphan_test")

    def test_report_runner_fetches_one_extra_row_to_detect_truncation(self) -> None:
        """Bound exports while retaining the function's deterministic order."""
        report = next(report for report in REPORTS if report.name == "items")
        arguments = WINDOW + (None,)
        _, rows = execute_report(self.database, report, arguments, limit=2)
        self.assertEqual(rows, self._rows(self._call(report.function, arguments))[:3])


def _standalone_equivalence_test(name: str):
    """Check one published SELECT's values, row order, and column names."""
    def test(self):
        signature = function_definitions()[name][0]
        parameters = example_parameters(name, signature)
        call = self._call(name, tuple(parameters.values()))
        query = standalone_queries()[name]
        self.assertEqual(self._rows(call), self._rows(query))
        with self.database.cursor() as cursor:
            cursor.execute(call)
            expected = [column.name for column in cursor.description]
            cursor.execute(query)
            self.assertEqual([column.name for column in cursor.description], expected)
    test.__doc__ = f"The standalone {name} SELECT matches the callable function."
    return test


for _name in function_definitions():
    setattr(ReportingIntegrationTests, f"test_standalone_{_name}", _standalone_equivalence_test(_name))


def _runner_equivalence_test(report):
    """Check one CLI catalog entry against direct SQL with each ID-array shape."""
    def test(self):
        for ids in (None, [], [1], [1, 2], [999]):
            with self.subTest(ids=ids):
                arguments = WINDOW + (ids,) * len(report.filters)
                if report.top_default is not None:
                    arguments += (report.top_default,)
                columns, rows = execute_report(self.database, report, arguments, limit=100)
                self.assertEqual(rows, self._rows(self._call(report.function, arguments)))
                with self.database.cursor() as cursor:
                    cursor.execute(self._call(report.function, arguments))
                    self.assertEqual(columns, tuple(column.name for column in cursor.description))
    test.__doc__ = f"The {report.name} runner matches {report.function} with typed bound arguments."
    return test


for _report in REPORTS:
    setattr(ReportingIntegrationTests, f"test_runner_{_report.function}", _runner_equivalence_test(_report))
