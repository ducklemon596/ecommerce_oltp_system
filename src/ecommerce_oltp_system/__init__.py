"""Synthetic data generation package for the e-commerce OLTP project."""

import argparse
from pathlib import Path

from .constants import ORDER_COUNT, ORDERS_PER_FILE, SEED
from .generator import generate_all_files, generate_and_write_data
from .generators.orders import print_summary


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the complete nine-table synthetic dataset."
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    parser.add_argument("--orders", type=int, default=ORDER_COUNT)
    parser.add_argument("--orders-per-file", type=int, default=ORDERS_PER_FILE)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument(
        "--base-only",
        action="store_true",
        help="Generate only the seven smaller base tables.",
    )
    return parser.parse_args()


def _print_base_summary(table_counts: dict[str, int], output_dir: Path) -> None:
    print(
        "Generated, validated, and wrote "
        f"{table_counts['brand']} brands, "
        f"{table_counts['category']} categories, "
        f"{table_counts['seller']} sellers, "
        f"{table_counts['product']} products, "
        f"{table_counts['customer']} customers, "
        f"{table_counts['promotion']} promotions, and "
        f"{table_counts['promotion_product']} promotion-product mappings "
        f"to {output_dir}."
    )


def main() -> None:
    """Generate all tables by default, with a base-only option."""

    args = _arguments()
    if args.base_only:
        data, paths = generate_and_write_data(args.seed, args.output_dir)
        table_counts = {
            "brand": len(data.brands),
            "category": len(data.categories),
            "seller": len(data.sellers),
            "product": len(data.products),
            "customer": len(data.customers),
            "promotion": len(data.promotions),
            "promotion_product": len(data.promotion_products),
        }
        _print_base_summary(table_counts, paths[0].parent)
        return

    table_counts, paths, order_stats = generate_all_files(
        seed=args.seed,
        output_dir=args.output_dir,
        order_count=args.orders,
        orders_per_file=args.orders_per_file,
    )
    _print_base_summary(table_counts, paths[0].parent)
    print_summary(order_stats)
