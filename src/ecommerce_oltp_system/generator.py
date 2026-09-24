"""Public orchestration API for one complete synthetic data generation session."""

import random
from pathlib import Path

from faker import Faker

from ecommerce_oltp_system.constants import (
    BRAND_COUNT,
    CATEGORY_TREE,
    CUSTOMER_COUNT,
    DISCOUNT_TYPES,
    FIXED_DISCOUNTS,
    GENDERS,
    MAIN_CATEGORY_COUNT,
    MAX_UNIQUE_VALUE_ATTEMPTS,
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
from ecommerce_oltp_system.exporter import write_data_files
from ecommerce_oltp_system.generators.catalog import (
    generate_brands,
    generate_categories,
    generate_products,
    generate_sellers,
)
from ecommerce_oltp_system.generators.customers import generate_customers
from ecommerce_oltp_system.generators.promotions import (
    generate_promotion_products,
    generate_promotions,
)
from ecommerce_oltp_system.models import GeneratedData, Record
from ecommerce_oltp_system.validators import (
    validate_brands,
    validate_categories,
    validate_customers,
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
    "generate_and_write_data",
    "generate_products",
    "generate_promotion_products",
    "generate_promotions",
    "generate_sellers",
    "validate_brands",
    "validate_categories",
    "validate_customers",
    "validate_products",
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
