"""Generators for brands, categories, sellers, and products."""

import random
from datetime import datetime
from decimal import Decimal

from faker import Faker

from ecommerce_oltp_system.constants import (
    BRAND_COUNT,
    CATEGORY_TREE,
    MAIN_CATEGORY_COUNT,
    PRODUCT_COUNT,
    SELLER_COUNT,
    SELLER_TYPES,
    WINDOW_END,
    WINDOW_START,
)
from ecommerce_oltp_system.models import Record


def generate_brands(fake: Faker) -> list[Record]:
    """Generate independent brand records."""

    used_names: set[str] = set()
    brands: list[Record] = []
    for _ in range(BRAND_COUNT):
        brands.append(
            {
                "brand_name": _unique_company(fake, used_names),
                "country": fake.country(),
                "created_at": fake.date_time_between(
                    start_date=WINDOW_START, end_date=WINDOW_END
                ),
            }
        )
    return brands


def _unique_company(fake: Faker, used_names: set[str]) -> str:
    """Return a Faker company name that is unique within a table."""

    while True:
        company = fake.company()
        if company not in used_names:
            used_names.add(company)
            return company


def generate_categories(fake: Faker) -> list[Record]:
    """Generate main categories first, then their temporally valid children."""

    categories: list[Record] = []
    main_categories: list[Record] = []

    for category_name in CATEGORY_TREE:
        category = {
            "category_name": category_name,
            "parent_category_ref": None,
            "level": 1,
            "created_at": fake.date_time_between(
                start_date=WINDOW_START, end_date=WINDOW_END
            ),
        }
        categories.append(category)
        main_categories.append(category)

    for parent in main_categories:
        for category_name in CATEGORY_TREE[parent["category_name"]]:
            categories.append(
                {
                    "category_name": category_name,
                    "parent_category_ref": parent,
                    "level": 2,
                    "created_at": fake.date_time_between(
                        start_date=parent["created_at"], end_date=WINDOW_END
                    ),
                }
            )
    return categories


def generate_sellers(fake: Faker) -> list[Record]:
    """Generate Vietnam-based sellers independent of product generation."""

    return [
        {
            "seller_name": fake.company(),
            "join_date": fake.date_between(
                start_date=WINDOW_START.date(), end_date=WINDOW_END.date()
            ),
            "created_at": fake.date_time_between(
                start_date=WINDOW_START, end_date=WINDOW_END
            ),
            "seller_type": random.choice(SELLER_TYPES),
            "rating": round(random.uniform(3.0, 5.0), 1),
            "country": "Vietnam",
        }
        for _ in range(SELLER_COUNT)
    ]


def generate_products(
    fake: Faker,
    brands: list[Record],
    categories: list[Record],
    sellers: list[Record],
) -> list[Record]:
    """Generate products using real dependency records for each foreign key."""

    subcategories = [category for category in categories if category["level"] == 2]
    return [
        _generate_product(fake, brands, subcategories, sellers)
        for _ in range(PRODUCT_COUNT)
    ]


def _generate_product(
    fake: Faker,
    brands: list[Record],
    categories: list[Record],
    sellers: list[Record],
) -> Record:
    brand = random.choice(brands)
    category = random.choice(categories)
    seller = random.choice(sellers)
    seller_join_datetime = datetime.combine(seller["join_date"], datetime.min.time())
    earliest_created_at = max(
        WINDOW_START,
        brand["created_at"],
        category["created_at"],
        seller_join_datetime,
        seller["created_at"],
    )

    return {
        "product_name": fake.catch_phrase(),
        "category_ref": category,
        "brand_ref": brand,
        "seller_ref": seller,
        "price": Decimal(str(random.uniform(100_000, 50_000_000))).quantize(
            Decimal("0.01")
        ),
        "stock_qty": random.randint(0, 500),
        "rating": round(random.uniform(3.0, 5.0), 1),
        "created_at": fake.date_time_between(
            start_date=earliest_created_at, end_date=WINDOW_END
        ),
        "is_active": random.choice((True, False)),
    }
