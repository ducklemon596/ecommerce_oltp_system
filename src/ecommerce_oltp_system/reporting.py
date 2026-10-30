"""CLI adapters for deployed PostgreSQL reporting functions; no business SQL."""

from __future__ import annotations

import argparse
import csv
import sys
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from uuid import uuid4

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import connection

from .loader.db.connection import database_config


@dataclass(frozen=True)
class Report:
    """Map a short CLI name to one SQL function and its ordered optional inputs."""

    name: str
    function: str
    description: str
    filters: tuple[str, ...] = ()
    top_default: int | None = None


# Input order follows functions.sql. Only names/signatures live here; PostgreSQL
# remains responsible for attribution, deletion rules, aggregation, and ranking.
REPORTS = (
    Report("monthly", "report_monthly_revenue", "Monthly item revenue, units, and distinct orders."),
    Report("daily", "report_daily_revenue", "Daily item revenue for matching products.", ("products",)),
    Report("seller-performance", "report_seller_performance", "Seller item revenue with category/brand filters.", ("categories", "brands")),
    Report("top-products-per-brand", "report_top_products_per_brand", "Top products within each brand.", ("sellers",), 10),
    Report("status", "report_order_status_summary", "Order counts and full order revenue by status.", ("sellers", "categories")),
    Report("monthly-orders", "report_monthly_order_revenue", "Monthly full-order revenue and order counts."),
    Report("orders", "report_orders_by_seller", "Order rows filtered by sellers and date.", ("sellers",)),
    Report("items", "report_items_by_product", "Order-item rows filtered by products and date.", ("products",)),
    Report("highest-orders", "report_highest_value_orders", "Highest-value orders in the date window.", top_default=1),
    Report("top-products", "report_top_products", "Global top products by quantity sold.", top_default=20),
    Report("seller-sales", "report_seller_sales", "Seller product types, orders, lines, units, and revenue.", ("sellers",)),
    Report("product-monthly", "report_product_monthly_revenue", "Product revenue and units per order month.", ("products",)),
)

# Convenience batches call existing functions; they are not benchmark sessions.
GROUPS = {
    "broad": ("monthly", "monthly-orders", "seller-sales", "seller-performance", "product-monthly"),
    "ranking": ("highest-orders", "top-products", "top-products-per-brand"),
    "drill-down": ("seller-performance", "top-products-per-brand", "orders", "status"),
}


def parse_ids(value: str) -> list[int] | None:
    """Parse optional ID arrays without losing the NULL versus empty distinction."""
    value = value.strip()
    if value.lower() == "null":
        return None
    if value in ("", "[]"):
        return []
    try:
        return [int(item.strip()) for item in value.split(",")]
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use comma-separated integer IDs, null, or an empty string/[]") from error


def parse_date(value: str) -> date:
    """Accept an ISO date for the existing start-inclusive/end-exclusive window."""
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use a valid ISO date, such as 2025-03-01") from error


def positive_limit(value: str) -> int:
    """Bound exported rows independently of a report's business Top-N input."""
    try:
        limit = int(value)
        if limit > 0:
            return limit
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("Export limit must be a positive integer")


def _common_options(parser: argparse.ArgumentParser, *, inherit: bool = False) -> None:
    """Share export/connection options between all-report and targeted execution.

    Child parsers suppress their defaults so options supplied before a report
    name are not overwritten by that report's parser.
    """
    defaults = {
        "start": date(2025, 3, 1), "end": date(2025, 4, 1), "limit": 50,
        "config": Path("database.ini"), "section": "postgresql",
        "output_dir": Path("reports/results"),
    }
    if inherit:
        defaults = dict.fromkeys(defaults, argparse.SUPPRESS)
    parser.add_argument("--start", type=parse_date, default=defaults["start"], metavar="YYYY-MM-DD", help="Inclusive start (default: 2025-03-01).")
    parser.add_argument("--end", type=parse_date, default=defaults["end"], metavar="YYYY-MM-DD", help="Exclusive end (default: 2025-04-01).")
    parser.add_argument("--limit", type=positive_limit, default=defaults["limit"], help="Maximum CSV rows per report (default: 50); does not change business Top-N.")
    parser.add_argument("--output-dir", type=Path, default=defaults["output_dir"], help="CSV destination (default: reports/results).")
    parser.add_argument("--config", type=Path, default=defaults["config"], help="PostgreSQL INI file (default: database.ini).")
    parser.add_argument("--section", default=defaults["section"], help="INI section (default: postgresql).")


def configure_parser(parser: argparse.ArgumentParser) -> None:
    """Register default/all exports, targeted exports, and database-free listing."""
    parser.description = "Save PostgreSQL reports as CSV files. Without a report name, export all reports."
    _common_options(parser)
    parser.set_defaults(handler=run_all)
    commands = parser.add_subparsers(dest="report_command")
    listing = commands.add_parser("list", help="List all reports, functions, and available filters.")
    listing.set_defaults(handler=list_reports)
    all_reports = commands.add_parser("all", help="Save all reports, or a selected subset with --only.")
    _common_options(all_reports, inherit=True)
    all_reports.add_argument("--only", nargs="+", choices=[report.name for report in REPORTS], help="Save only these reports (space-separated names).")
    all_reports.set_defaults(handler=run_all)
    for name, members in GROUPS.items():
        group = commands.add_parser(name, help=f"Export {len(members)} {name} reports into a category directory.")
        _common_options(group, inherit=True)
        filters = sorted({key for report in REPORTS if report.name in members for key in report.filters})
        for key in filters:
            group.add_argument(f"--{key}", type=parse_ids, default=None, metavar="IDS",
                               help=f"Filter reports supporting {key}; others retain their own inputs.")
        group.add_argument("--top", type=int, default=None, help="Override business Top-N for ranking functions in this category.")
        group.set_defaults(handler=run_group, group=name, only=members)
    for report in REPORTS:
        command = commands.add_parser(report.name, help=report.description, description=report.description)
        _common_options(command, inherit=True)
        for name in report.filters:
            command.add_argument(f"--{name}", type=parse_ids, default=None, metavar="IDS", help='Comma-separated IDs; omitted/null = no filter; "" or [] = no matches.')
        if report.top_default is not None:
            command.add_argument("--top", type=int, default=report.top_default, help=f"Business Top-N (default: {report.top_default}; <= 0 returns no rows).")
        command.set_defaults(handler=run, report=report)


def execute_report(database: connection, report: Report, arguments: tuple, limit: int = 50) -> tuple[tuple[str, ...], list[tuple]]:
    """Call one whitelisted function with bound values, returning columns and rows.

    ``arguments`` contains start/end dates, the report's ordered ID arrays, and
    Top-N when applicable. Fetch at most ``limit + 1`` rows so the CLI can flag
    truncation without buffering an unbounded order/item export. The caller owns
    connection/transaction lifetime; this helper never installs SQL or commits.
    """
    if report not in REPORTS:
        raise ValueError("Unknown report")
    if limit <= 0:
        raise ValueError("Export limit must be positive")
    types = ["date", "date"] + ["integer[]"] * len(report.filters)
    if report.top_default is not None:
        types.append("integer")
    if len(arguments) != len(types):
        raise ValueError("Report arguments do not match the function signature")
    # Function identifiers and casts come only from the catalog, never CLI text.
    placeholders = sql.SQL(", ").join(sql.SQL("%s::{}").format(sql.SQL(kind)) for kind in types)
    statement = sql.SQL("SELECT * FROM {}({}) LIMIT %s").format(sql.Identifier(report.function), placeholders)
    with database.cursor() as cursor:
        cursor.execute(statement, (*arguments, limit + 1))
        return tuple(column.name for column in cursor.description), cursor.fetchall()


def print_table(columns: tuple[str, ...], rows: list[tuple]) -> None:
    """Print a small result with headers, preserving Decimal/date display values."""
    def cell(value) -> str:
        """Keep database text on one terminal row, including embedded newlines."""
        return "NULL" if value is None else str(value).replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")

    cells = [tuple(cell(value) for value in row) for row in rows]
    widths = [max([len(column), *(len(row[index]) for row in cells)]) for index, column in enumerate(columns)]
    print(" | ".join(column.ljust(width) for column, width in zip(columns, widths)))
    print("-+-".join("-" * width for width in widths))
    for row in cells:
        print(" | ".join(value.ljust(width) for value, width in zip(row, widths)))


def list_reports(_args: argparse.Namespace) -> None:
    """List the static catalog without requiring a database or configuration file."""
    rows = []
    for report in REPORTS:
        options = [f"--{name}" for name in report.filters]
        if report.top_default is not None:
            options.append(f"--top (default {report.top_default})")
        rows.append((report.name, report.function, ", ".join(options) or "—"))
    print_table(("report", "PostgreSQL function", "report options"), rows)
    print("All reports: --start / --end (March 2025 by default), --limit, --output-dir, --config, --section.")
    print("Categories: " + ", ".join(GROUPS) + ". Use uv run ecommerce report <category|report> --help.")


def save_csv(report: Report, args: argparse.Namespace, columns: tuple[str, ...], rows: list[tuple]) -> Path:
    """Write one bounded result to a new UTF-8 CSV, keeping previous exports.

    Filenames include the report, date window, and unique run suffix. An empty
    result still writes headers. A failed write removes only its own partial file.
    """
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / f"{report.name}_{args.start}_{args.end}_{uuid4().hex[:12]}.csv"
    output = path.open("x", encoding="utf-8", newline="")
    try:
        with output:
            writer = csv.writer(output)
            writer.writerow(columns)
            writer.writerows(rows)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def run(args: argparse.Namespace) -> None:
    """Read a deployed function and save its result as CSV, not a terminal table.

    Reuses the loader's INI configuration. Connections close after success or
    failure; reporting never deploys functions or changes application records.
    """
    validate_window(args)
    arguments = (args.start, args.end, *(getattr(args, name) for name in args.report.filters))
    if args.report.top_default is not None:
        arguments += (args.top,)
    try:
        with closing(psycopg2.connect(**database_config(args.config, args.section))) as database:
            database.set_session(readonly=True)
            with database:
                columns, rows = execute_report(database, args.report, arguments, args.limit)
        path = save_csv(args.report, args, columns, rows[:args.limit])
    except psycopg2.errors.UndefinedFunction as error:
        raise SystemExit("Reporting function unavailable. Run uv run ecommerce setup --indexes none to deploy database/reporting/functions.sql; see docs/usage/README.md.") from error
    except (psycopg2.Error, OSError, ValueError) as error:
        raise SystemExit(f"Cannot run report: {error}") from error
    print(f"SAVED {path} ({min(len(rows), args.limit)} rows).")
    if len(rows) > args.limit:
        print(f"Limited to {args.limit} rows; more rows exist. Increase --limit to export more.")


def run_all(args: argparse.Namespace) -> None:
    """Save each requested report independently, continuing past individual errors.

    All-report exports use NULL filters and each function's default Top-N. Failed
    reports create no CSV; successful exports remain available. Exit nonzero if
    any report failed, so incomplete runs cannot be mistaken for full success.
    """
    validate_window(args)
    selected = getattr(args, "only", None)
    reports = [report for report in REPORTS if selected is None or report.name in selected]
    failures = []
    for report in reports:
        options = {**vars(args), "report": report,
                   "top": args.top if getattr(args, "top", None) is not None else report.top_default}
        options.update({name: getattr(args, name, None) for name in report.filters})
        try:
            run(argparse.Namespace(**options))
        except SystemExit as error:
            if error.code == 0:
                raise
            failures.append(report.name)
            print(f"FAILED {report.name}: {error}", file=sys.stderr)
    if failures:
        raise SystemExit(f"Saved {len(reports) - len(failures)}/{len(reports)} reports. Failed: {', '.join(failures)}.")


def validate_window(args: argparse.Namespace) -> None:
    """Reject empty or reversed windows before opening any report connection."""
    if args.start >= args.end:
        raise SystemExit("Invalid date window: --start must be earlier than --end (end is exclusive).")


def run_group(args: argparse.Namespace) -> None:
    """Reuse batch exports with category-specific output and supported filters."""
    options = {**vars(args), "output_dir": args.output_dir / args.group}
    run_all(argparse.Namespace(**options))


def main(argv: list[str] | None = None) -> None:
    """Expose ``uv run report`` using the same parser and handlers as ecommerce."""
    parser = argparse.ArgumentParser(prog="report")
    configure_parser(parser)
    args = parser.parse_args(argv)
    args.handler(args)
