"""Synthetic data generation package for the e-commerce OLTP project."""

from .generator import SEED, generate_data


def main() -> None:
    """Run one complete validated synthetic-data generation session."""

    data = generate_data(SEED)
    print(
        "Generated and validated "
        f"{len(data.brands)} brands, {len(data.categories)} categories, "
        f"{len(data.sellers)} sellers, {len(data.products)} products, "
        f"{len(data.customers)} customers, {len(data.promotions)} promotions, and "
        f"{len(data.promotion_products)} promotion-product mappings."
    )
