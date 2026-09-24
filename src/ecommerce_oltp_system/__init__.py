"""Synthetic data generation package for the e-commerce OLTP project."""

from .generator import SEED, generate_and_write_data


def main() -> None:
    """Generate, validate, and write one complete synthetic dataset."""

    data, paths = generate_and_write_data(SEED)
    print(
        "Generated, validated, and wrote "
        f"{len(data.brands)} brands, {len(data.categories)} categories, "
        f"{len(data.sellers)} sellers, {len(data.products)} products, "
        f"{len(data.customers)} customers, {len(data.promotions)} promotions, and "
        f"{len(data.promotion_products)} promotion-product mappings "
        f"to {paths[0].parent}."
    )
