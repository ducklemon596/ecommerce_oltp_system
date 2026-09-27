"""Single command for the complete synthetic-data generation pipeline."""

import argparse
from pathlib import Path

from .generators.orders.generator import print_summary
from .generators.pipeline import generate_all_files, generate_and_write_data
from .generators.config import ORDER_COUNT, ORDERS_PER_FILE, SEED
from .generators.models import GeneratedData


def _arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate, validate, and write all nine synthetic tables."
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    parser.add_argument("--orders", type=int, default=ORDER_COUNT)
    parser.add_argument("--orders-per-file", type=int, default=ORDERS_PER_FILE)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument(
        "--base-only",
        action="store_true",
        help="Generate only the seven smaller master/dependent tables.",
    )
    return parser.parse_args()


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


def main() -> None:
    """Run the dependency-aware end-to-end generation pipeline."""

    args = _arguments()
    if args.base_only:
        data, paths = generate_and_write_data(args.seed, args.output_dir)
        _print_base_summary(data, paths[0].parent)
        return

    table_counts, paths, order_stats = generate_all_files(
        seed=args.seed,
        output_dir=args.output_dir,
        order_count=args.orders,
        orders_per_file=args.orders_per_file,
    )
    print(
        "Generated, validated, and wrote "
        f"{sum(table_counts.values())} reference rows to {paths[0].parent}."
    )
    print_summary(order_stats)


if __name__ == "__main__":
    main()
