"""Options and dispatch for ``uv run ecommerce generate``."""

import argparse
from pathlib import Path

from .generators.orders.generator import generate_order_files, print_summary
from .generators.pipeline import generate_all_files, generate_and_write_data
from .generators.config import ORDER_COUNT, ORDERS_PER_FILE, SEED
from .generators.models import GeneratedData


def configure_parser(parser: argparse.ArgumentParser) -> None:
    """Register full, reference-only, and orders-only generation on the CLI."""
    parser.add_argument("--output-dir", type=Path, help="Output root (default: data, or --data-dir in orders-only mode).")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="Existing customer/product CSV root; used only with --orders-only.")
    parser.add_argument("--orders", type=int, default=ORDER_COUNT)
    parser.add_argument("--orders-per-file", type=int, default=ORDERS_PER_FILE)
    parser.add_argument("--seed", type=int, default=SEED)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--base-only",
        action="store_true",
        help="Generate only the seven smaller master/dependent tables.",
    )
    modes.add_argument("--orders-only", action="store_true", help="Reuse existing customer/product CSVs without regenerating reference tables.")


def _print_base_summary(data: GeneratedData, output_dir: Path) -> None:
    """Print a summary for generated reference tables."""
    print(
        "Generated, validated, and wrote "
        f"{len(data.brands)} brands, "
        f"{len(data.categories)} categories, "
        f"{len(data.sellers)} sellers, "
        f"{len(data.products)} products, "
        f"{len(data.customers)} customers, "
        f"{len(data.promotions)} promotions, and "
        f"{len(data.promotion_products)} promotion-product mappings "
        f"to {output_dir}."
    )


def run(args: argparse.Namespace) -> None:
    """Generate and validate reference tables and streamed parts, writing CSVs.

    Called by the application CLI with parsed dataset options. ``base_only``
    writes just the seven reference/dependent tables; otherwise all nine tables
    are generated without retaining the complete order dataset in memory.
    ``orders_only`` reuses reference files instead of regenerating them.
    """
    if args.orders_only:
        stats = generate_order_files(
            data_dir=args.data_dir,
            output_dir=args.output_dir,
            order_count=args.orders,
            orders_per_file=args.orders_per_file,
            seed=args.seed,
        )
        print_summary(stats)
        return

    output_dir = args.output_dir or Path("data")
    if args.base_only:
        data, paths = generate_and_write_data(args.seed, output_dir)
        _print_base_summary(data, paths[0].parent)
        return

    table_counts, paths, order_stats = generate_all_files(
        seed=args.seed,
        output_dir=output_dir,
        order_count=args.orders,
        orders_per_file=args.orders_per_file,
    )
    print(
        "Generated, validated, and wrote "
        f"{sum(table_counts.values())} reference rows to {paths[0].parent}."
    )
    print_summary(order_stats)
