"""Generate a small, relationally consistent e-commerce dataset.

This module deliberately contains only the first four tables from the project:
brand, category, seller, and product.  It keeps the generated records in memory
so the data can be validated as one complete generation session before a future
database-loading step is introduced.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from faker import Faker


SEED = 42
WINDOW_START = datetime(2025, 1, 1, 0, 0, 0)
WINDOW_END = datetime(2025, 5, 31, 23, 59, 59)

BRAND_COUNT = 20
MAIN_CATEGORY_COUNT = 5
SUBCATEGORY_COUNT = 20
SELLER_COUNT = 50
PRODUCT_COUNT = 3_000

SELLER_TYPES = ("Official", "Marketplace")

# Four sub-categories are assigned to each main category.  Static names are
# clearer and more useful for e-commerce data than arbitrary generated text.
CATEGORY_TREE = {
    "Electronics": ("Mobile Phones", "Laptops", "Audio", "Smart Home"),
    "Fashion": ("Men's Clothing", "Women's Clothing", "Shoes", "Accessories"),
    "Home & Living": ("Furniture", "Kitchenware", "Bedding", "Home Decor"),
    "Beauty & Health": ("Skincare", "Makeup", "Personal Care", "Wellness"),
    "Sports & Outdoors": ("Fitness", "Cycling", "Camping", "Sportswear"),
}


Record = dict[str, Any]


@dataclass(frozen=True)
class GeneratedData:
    """The complete output of one generation session."""

    brands: list[Record]
    categories: list[Record]
    sellers: list[Record]
    products: list[Record]


def _unique_company(fake: Faker, used_names: set[str]) -> str:
    """Return a Faker company name that is unique within a table."""

    while True:
        company = fake.company()
        if company not in used_names:
            used_names.add(company)
            return company


def generate_brands(fake: Faker) -> list[Record]:
    """Generate independent brand records."""

    used_names: set[str] = set()
    return [
        {
            "brand_id": brand_id,
            "brand_name": _unique_company(fake, used_names),
            "country": fake.country(),
            "created_at": fake.date_time_between(
                start_date=WINDOW_START, end_date=WINDOW_END
            ),
        }
        for brand_id in range(1, BRAND_COUNT + 1)
    ]


def generate_categories(fake: Faker) -> list[Record]:
    """Generate main categories first, then their temporally valid children."""

    categories: list[Record] = []
    main_categories: list[Record] = []

    for category_id, category_name in enumerate(CATEGORY_TREE, start=1):
        category = {
            "category_id": category_id,
            "category_name": category_name,
            "parent_category_id": None,
            "level": 1,
            "created_at": fake.date_time_between(
                start_date=WINDOW_START, end_date=WINDOW_END
            ),
        }
        categories.append(category)
        main_categories.append(category)

    category_id = MAIN_CATEGORY_COUNT + 1
    for parent in main_categories:
        for category_name in CATEGORY_TREE[parent["category_name"]]:
            categories.append(
                {
                    "category_id": category_id,
                    "category_name": category_name,
                    "parent_category_id": parent["category_id"],
                    "level": 2,
                    "created_at": fake.date_time_between(
                        start_date=parent["created_at"], end_date=WINDOW_END
                    ),
                }
            )
            category_id += 1

    return categories


def generate_sellers(fake: Faker) -> list[Record]:
    """Generate Vietnam-based sellers independent of product generation."""

    return [
        {
            "seller_id": seller_id,
            "seller_name": fake.company(),
            "join_date": fake.date_between(
                start_date=WINDOW_START.date(), end_date=WINDOW_END.date()
            ),
            "seller_type": random.choice(SELLER_TYPES),
            "rating": round(random.uniform(3.0, 5.0), 1),
            "country": "Vietnam",
        }
        for seller_id in range(1, SELLER_COUNT + 1)
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
        _generate_product(product_id, fake, brands, subcategories, sellers)
        for product_id in range(1, PRODUCT_COUNT + 1)
    ]


def _generate_product(
    product_id: int,
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
    )

    return {
        "product_id": product_id,
        "product_name": fake.catch_phrase(),
        "category_id": category["category_id"],
        "brand_id": brand["brand_id"],
        "seller_id": seller["seller_id"],
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


def validate_brands(brands: list[Record]) -> None:
    assert len(brands) == BRAND_COUNT, "Expected 20 brands"
    assert len({brand["brand_name"] for brand in brands}) == BRAND_COUNT, (
        "Brand names must be unique"
    )
    for brand in brands:
        assert WINDOW_START <= brand["created_at"] <= WINDOW_END, (
            "Brand created_at is outside the generation window"
        )


def validate_categories(categories: list[Record]) -> None:
    assert len(categories) == MAIN_CATEGORY_COUNT + SUBCATEGORY_COUNT, (
        "Expected 25 categories"
    )
    assert len({category["category_name"] for category in categories}) == len(categories), (
        "Category names must be unique"
    )

    category_by_id = {category["category_id"]: category for category in categories}
    main_categories = [category for category in categories if category["level"] == 1]
    subcategories = [category for category in categories if category["level"] == 2]
    assert len(main_categories) == MAIN_CATEGORY_COUNT, "Expected 5 main categories"
    assert len(subcategories) == SUBCATEGORY_COUNT, "Expected 20 sub-categories"

    for category in categories:
        assert WINDOW_START <= category["created_at"] <= WINDOW_END, (
            "Category created_at is outside the generation window"
        )
        if category["level"] == 1:
            assert category["parent_category_id"] is None, (
                "A level-1 category cannot have a parent"
            )
        else:
            parent = category_by_id.get(category["parent_category_id"])
            assert parent is not None, "A sub-category must reference a valid parent"
            assert parent["level"] == 1, "A sub-category parent must be level 1"
            assert parent["created_at"] <= category["created_at"], (
                "A parent category cannot be newer than its child"
            )


def validate_sellers(sellers: list[Record]) -> None:
    assert len(sellers) == SELLER_COUNT, "Expected 50 sellers"
    for seller in sellers:
        assert seller["seller_type"] in SELLER_TYPES, "Invalid seller type"
        assert 0 <= seller["rating"] <= 5, "Seller rating must be between 0 and 5"
        assert seller["country"] == "Vietnam", "Seller country must be Vietnam"
        assert WINDOW_START.date() <= seller["join_date"] <= WINDOW_END.date(), (
            "Seller join_date is outside the generation window"
        )


def validate_products(
    products: list[Record],
    brands: list[Record],
    categories: list[Record],
    sellers: list[Record],
) -> None:
    assert len(products) == PRODUCT_COUNT, "Expected 3,000 products"
    brands_by_id = {brand["brand_id"]: brand for brand in brands}
    categories_by_id = {category["category_id"]: category for category in categories}
    sellers_by_id = {seller["seller_id"]: seller for seller in sellers}

    for product in products:
        brand = brands_by_id.get(product["brand_id"])
        category = categories_by_id.get(product["category_id"])
        seller = sellers_by_id.get(product["seller_id"])
        assert brand is not None, "Product has an invalid brand_id"
        assert category is not None, "Product has an invalid category_id"
        assert seller is not None, "Product has an invalid seller_id"
        assert category["level"] == 2, "Products should use sub-categories"
        assert product["price"] > 0, "Product price must be positive"
        assert product["stock_qty"] >= 0, "Product stock cannot be negative"
        assert 0 <= product["rating"] <= 5, "Product rating must be between 0 and 5"
        assert WINDOW_START <= product["created_at"] <= WINDOW_END, (
            "Product created_at is outside the generation window"
        )
        assert brand["created_at"] <= product["created_at"], (
            "Product predates its brand"
        )
        assert category["created_at"] <= product["created_at"], (
            "Product predates its category"
        )
        seller_join_datetime = datetime.combine(seller["join_date"], datetime.min.time())
        assert seller_join_datetime <= product["created_at"], (
            "Product predates its seller"
        )


def generate_data(seed: int = SEED) -> GeneratedData:
    """Generate and validate one complete deterministic data session."""

    random.seed(seed)
    Faker.seed(seed)
    fake = Faker()

    brands = generate_brands(fake)
    sellers = generate_sellers(fake)
    categories = generate_categories(fake)
    products = generate_products(fake, brands, categories, sellers)

    validate_brands(brands)
    validate_categories(categories)
    validate_sellers(sellers)
    validate_products(products, brands, categories, sellers)

    return GeneratedData(brands, categories, sellers, products)
