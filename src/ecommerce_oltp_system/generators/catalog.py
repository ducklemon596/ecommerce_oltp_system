"""Generators for brands, categories, sellers, and products."""

import random
from datetime import datetime
from decimal import Decimal

from faker import Faker

from ecommerce_oltp_system.shared.constants import (
    BRAND_COUNT,
    CATEGORY_TREE,
    CREATED_BY,
    MAIN_CATEGORY_COUNT,
    PRODUCT_COUNT,
    SELLER_COUNT,
    SELLER_TYPES,
    WINDOW_END,
    WINDOW_START,
)
from ecommerce_oltp_system.shared.models import Record


def generate_brands(fake: Faker) -> list[Record]:
    """Generate independent brand records."""

    used_names: set[str] = set()
    brands: list[Record] = []
    for position in range(1, BRAND_COUNT + 1):
        brands.append(
            {
                "brand_code": f"BRD-{position:05d}",
                "brand_name": _unique_company(fake, used_names),
                "country": fake.country(),
                "created_at": fake.date_time_between(
                    start_date=WINDOW_START, end_date=WINDOW_END
                ),
                **_audit_fields(),
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
    for position, category_name in enumerate(CATEGORY_TREE, start=1):
        category = {
            "category_code": f"CAT-{position:05d}",
            "category_name": category_name,
            "parent_category_id": None,
            "level": 1,
            "created_at": fake.date_time_between(
                start_date=WINDOW_START, end_date=WINDOW_END
            ),
            **_audit_fields(),
        }
        categories.append(category)

    subcategory_position = MAIN_CATEGORY_COUNT + 1
    for parent_category_id, category_names in enumerate(CATEGORY_TREE.values(), start=1):
        parent = categories[parent_category_id - 1]
        for category_name in category_names:
            categories.append(
                {
                    "category_code": f"CAT-{subcategory_position:05d}",
                    "category_name": category_name,
                    "parent_category_id": parent_category_id,
                    "level": 2,
                    "created_at": fake.date_time_between(
                        start_date=parent["created_at"], end_date=WINDOW_END
                    ),
                    **_audit_fields(),
                }
            )
            subcategory_position += 1
    return categories


def generate_sellers(fake: Faker) -> list[Record]:
    """Generate Vietnam-based sellers independent of product generation."""

    return [
        {
            "seller_code": f"SEL-{position:05d}",
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
            **_audit_fields(),
        }
        for position in range(1, SELLER_COUNT + 1)
    ]


def generate_products(
    fake: Faker,
    brands: list[Record],
    categories: list[Record],
    sellers: list[Record],
) -> list[Record]:
    """Generate products using real dependency records for each foreign key."""

    subcategory_ids = list(range(MAIN_CATEGORY_COUNT + 1, len(categories) + 1))
    return [
        _generate_product(position, fake, brands, categories, sellers, subcategory_ids)
        for position in range(1, PRODUCT_COUNT + 1)
    ]


def _generate_product(
    position: int,
    fake: Faker,
    brands: list[Record],
    categories: list[Record],
    sellers: list[Record],
    subcategory_ids: list[int],
) -> Record:
    brand_id = random.randint(1, BRAND_COUNT)
    category_id = random.choice(subcategory_ids)
    seller_id = random.randint(1, SELLER_COUNT)
    brand = brands[brand_id - 1]
    category = categories[category_id - 1]
    seller = sellers[seller_id - 1]
    seller_join_datetime = datetime.combine(seller["join_date"], datetime.min.time())
    earliest_created_at = max(
        WINDOW_START,
        brand["created_at"],
        category["created_at"],
        seller_join_datetime,
        seller["created_at"],
    )

    return {
        "product_code": f"PRD-{position:06d}",
        "product_name": fake.catch_phrase(),
        "category_id": category_id,
        "brand_id": brand_id,
        "seller_id": seller_id,
        "price": Decimal(str(random.uniform(100_000, 50_000_000))).quantize(
            Decimal("0.01")
        ),
        "stock_qty": random.randint(0, 500),
        "rating": round(random.uniform(3.0, 5.0), 1),
        "created_at": fake.date_time_between(
            start_date=earliest_created_at, end_date=WINDOW_END
        ),
        "is_active": random.choice((True, False)),
        **_audit_fields(),
    }


def _audit_fields() -> Record:
    return {
        "created_by": CREATED_BY,
        "updated_at": None,
        "updated_by": None,
        "deleted_at": None,
        "deleted_by": None,
        "is_deleted": False,
        "loaded_at": None,
    }
