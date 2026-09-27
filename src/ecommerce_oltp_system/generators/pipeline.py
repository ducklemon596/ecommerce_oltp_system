"""Public orchestration API for one complete synthetic data generation session."""

import random
from pathlib import Path

from faker import Faker

from ecommerce_oltp_system.generators.constants import (
    BRAND_COUNT,
    CATEGORY_TREE,
    CUSTOMER_COUNT,
    DISCOUNT_TYPES,
    FIXED_DISCOUNTS,
    GENDERS,
    MAIN_CATEGORY_COUNT,
    MAX_UNIQUE_VALUE_ATTEMPTS,
    ORDER_COUNT,
    ORDERS_PER_FILE,
    PRODUCT_COUNT,
    PROMOTION_TYPES,
    PROMOTION_COUNT,
    PROMOTION_PRODUCT_COUNT,
    PERCENTAGE_DISCOUNTS,
    SEED,
    SELLER_COUNT,
    SELLER_TYPES,
    SUBCATEGORY_COUNT,
    WINDOW_END,
    WINDOW_START,
)
from ecommerce_oltp_system.generators.exporter import write_data_files
from ecommerce_oltp_system.generators.catalog import (
    generate_brands,
    generate_categories,
    generate_products,
    generate_sellers,
)
from ecommerce_oltp_system.generators.customers import generate_customers
from ecommerce_oltp_system.generators.orders import (
    OrderGenerationStats,
    generate_order_files,
)
from ecommerce_oltp_system.generators.promotions import (
    generate_promotion_products,
    generate_promotions,
)
from ecommerce_oltp_system.generators.models import GeneratedData, Record
from ecommerce_oltp_system.generators.validators import (
    validate_brands,
    validate_categories,
    validate_customers,
    validate_order,
    validate_order_items,
    validate_products,
    validate_promotion_products,
    validate_promotions,
    validate_sellers,
)

__all__ = [
    "BRAND_COUNT",
    "CATEGORY_TREE",
    "CUSTOMER_COUNT",
    "DISCOUNT_TYPES",
    "FIXED_DISCOUNTS",
    "GENDERS",
    "MAIN_CATEGORY_COUNT",
    "MAX_UNIQUE_VALUE_ATTEMPTS",
    "ORDER_COUNT",
    "ORDERS_PER_FILE",
    "OrderGenerationStats",
    "PERCENTAGE_DISCOUNTS",
    "PRODUCT_COUNT",
    "PROMOTION_COUNT",
    "PROMOTION_PRODUCT_COUNT",
    "PROMOTION_TYPES",
    "Record",
    "SEED",
    "SELLER_COUNT",
    "SELLER_TYPES",
    "SUBCATEGORY_COUNT",
    "WINDOW_END",
    "WINDOW_START",
    "GeneratedData",
    "generate_brands",
    "generate_categories",
    "generate_customers",
    "generate_data",
    "generate_all_files",
    "generate_and_write_data",
    "generate_products",
    "generate_promotion_products",
    "generate_promotions",
    "generate_sellers",
    "validate_brands",
    "validate_categories",
    "validate_customers",
    "validate_products",
    "validate_order",
    "validate_order_items",
    "validate_promotion_products",
    "validate_promotions",
    "validate_sellers",
    "write_data_files",
]


def generate_data(seed: int = SEED) -> GeneratedData:
    """Generate and validate one complete deterministic data session."""

    random.seed(seed)
    Faker.seed(seed)
    fake = Faker()

    brands = generate_brands(fake)
    sellers = generate_sellers(fake)
    categories = generate_categories(fake)
    products = generate_products(fake, brands, categories, sellers)
    customer_fake = Faker("vi_VN")
    customer_fake.seed_instance(seed)
    customers = generate_customers(customer_fake)
    promotions = generate_promotions(fake, products)
    promotion_products = generate_promotion_products(fake, promotions, products)

    validate_brands(brands)
    validate_categories(categories)
    validate_sellers(sellers)
    validate_products(products, brands, categories, sellers)
    validate_customers(customers)
    validate_promotions(promotions)
    validate_promotion_products(promotion_products, promotions, products)

    return GeneratedData(
        brands=brands,
        categories=categories,
        sellers=sellers,
        products=products,
        customers=customers,
        promotions=promotions,
        promotion_products=promotion_products,
    )


def generate_and_write_data(
    seed: int = SEED, output_dir: str | Path = "data"
) -> tuple[GeneratedData, list[Path]]:
    """Generate, validate, and write one complete dataset."""

    data = generate_data(seed)
    paths = write_data_files(data, output_dir)
    return data, paths


def generate_all_files(
    seed: int = SEED,
    output_dir: str | Path = "data",
    order_count: int = ORDER_COUNT,
    orders_per_file: int = ORDERS_PER_FILE,
    show_progress: bool = True,
) -> tuple[dict[str, int], list[Path], OrderGenerationStats]:
    """Generate all nine tables, streaming the two high-volume datasets."""

    data, paths = generate_and_write_data(seed, output_dir)
    table_counts = {
        "brand": len(data.brands),
        "category": len(data.categories),
        "seller": len(data.sellers),
        "product": len(data.products),
        "customer": len(data.customers),
        "promotion": len(data.promotions),
        "promotion_product": len(data.promotion_products),
    }
    del data

    order_stats = generate_order_files(
        data_dir=output_dir,
        output_dir=output_dir,
        order_count=order_count,
        orders_per_file=orders_per_file,
        seed=seed,
        show_progress=show_progress,
    )
    return table_counts, paths, order_stats
