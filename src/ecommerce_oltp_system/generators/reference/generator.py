"""Reference and dependent table generation before order streaming."""

import random
from datetime import datetime
from decimal import Decimal
from typing import Callable

from faker import Faker

from ..config import (
    BRAND_COUNT,
    CATEGORY_TREE,
    CREATED_BY,
    CUSTOMER_COUNT,
    DISCOUNT_TYPES,
    FIXED_DISCOUNTS,
    GENDERS,
    MAIN_CATEGORY_COUNT,
    MAX_UNIQUE_VALUE_ATTEMPTS,
    PERCENTAGE_DISCOUNTS,
    PRE_WINDOW_END,
    PRE_WINDOW_PRODUCT_SHARE,
    PRE_WINDOW_START,
    PRODUCT_COUNT,
    PRODUCT_ROLLOUT_END,
    PROMOTION_COUNT,
    PROMOTION_PRODUCT_COUNT,
    PROMOTION_TYPES,
    SELLER_COUNT,
    SELLER_TYPES,
    WINDOW_END,
    WINDOW_START,
)
from ..models import Record


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
                    start_date=PRE_WINDOW_START, end_date=PRE_WINDOW_END
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
                start_date=PRE_WINDOW_START, end_date=PRE_WINDOW_END
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
                        start_date=parent["created_at"], end_date=PRE_WINDOW_END
                    ),
                    **_audit_fields(),
                }
            )
            subcategory_position += 1
    return categories


def generate_sellers(fake: Faker) -> list[Record]:
    """Generate Vietnam-based sellers independent of product generation."""

    sellers: list[Record] = []
    for position in range(1, SELLER_COUNT + 1):
        join_date = fake.date_between(
            start_date=PRE_WINDOW_START.date(), end_date=PRE_WINDOW_END.date()
        )
        sellers.append(
            {
                "seller_code": f"SEL-{position:05d}",
                "seller_name": fake.company(),
                "join_date": join_date,
                "created_at": fake.date_time_between(
                    start_date=datetime.combine(join_date, datetime.min.time()),
                    end_date=PRE_WINDOW_END,
                ),
                "seller_type": random.choice(SELLER_TYPES),
                "rating": round(random.uniform(3.0, 5.0), 1),
                "country": "Vietnam",
                **_audit_fields(),
            }
        )
    return sellers


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
    """Generate one product with valid catalog dependencies."""
    brand_id = random.randint(1, BRAND_COUNT)
    category_id = random.choice(subcategory_ids)
    seller_id = random.randint(1, SELLER_COUNT)
    brand = brands[brand_id - 1]
    category = categories[category_id - 1]
    seller = sellers[seller_id - 1]
    seller_join_datetime = datetime.combine(seller["join_date"], datetime.min.time())
    earliest_created_at = max(
        PRE_WINDOW_START,
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
            start_date=earliest_created_at,
            end_date=(
                PRE_WINDOW_END
                if random.random() < PRE_WINDOW_PRODUCT_SHARE
                else PRODUCT_ROLLOUT_END
            ),
        ),
        "is_active": random.choice((True, False)),
        **_audit_fields(),
    }


def _audit_fields() -> Record:
    """Return default audit fields for a generated record."""
    return {
        "created_by": CREATED_BY,
        "updated_at": None,
        "updated_by": None,
        "deleted_at": None,
        "deleted_by": None,
        "is_deleted": False,
        "loaded_at": None,
    }



def generate_customers(fake: Faker) -> list[Record]:
    """Generate independent Vietnamese customer records with unique contacts."""

    used_emails: set[str] = set()
    used_phones: set[str] = set()
    customers: list[Record] = []
    for position in range(1, CUSTOMER_COUNT + 1):
        customers.append(
            {
                "customer_code": f"CUS-{position:06d}",
                "customer_name": fake.name(),
                "email": _unique_value(
                    lambda: _customer_email(fake),
                    used_emails,
                    "customer email",
                ),
                "phone": _unique_value(fake.phone_number, used_phones, "customer phone"),
                "gender": random.choice(GENDERS),
                "address": fake.address(),
                "city": fake.city(),
                "created_at": fake.date_time_between(
                    start_date=WINDOW_START, end_date=WINDOW_END
                ),
                "created_by": CREATED_BY,
                "updated_at": None,
                "updated_by": None,
                "deleted_at": None,
                "deleted_by": None,
                "is_deleted": False,
                "loaded_at": None,
            }
        )
    return customers


def _unique_value(
    value_factory: Callable[[], str], used_values: set[str], value_name: str
) -> str:
    """Generate one unique value or fail if Faker's value space is exhausted."""

    for _ in range(MAX_UNIQUE_VALUE_ATTEMPTS):
        value = value_factory()
        if value not in used_values:
            used_values.add(value)
            return value
    raise ValueError(f"Unable to generate a unique {value_name}")


def _customer_email(fake: Faker) -> str:
    """Keep a Faker email realistic while making its local part scalable and unique."""

    local_part, domain = fake.email().rsplit("@", maxsplit=1)
    unique_suffix = str(fake.uuid4()).replace("-", "")[:12]
    return f"{local_part}.{unique_suffix}@{domain}"



def generate_promotions(fake: Faker, products: list[Record]) -> list[Record]:
    """Generate campaigns whose fixed discounts can be applied to products."""

    assert products, "Products are required before promotions can be generated"
    lowest_product_price = min(product["price"] for product in products)
    fixed_discounts = [
        discount for discount in FIXED_DISCOUNTS if discount <= lowest_product_price
    ]
    assert fixed_discounts, "No valid fixed discount is compatible with products"

    promotions: list[Record] = []
    for position in range(1, PROMOTION_COUNT + 1):
        created_at = fake.date_time_between(start_date=WINDOW_START, end_date=WINDOW_END)
        start_date = fake.date_between(
            start_date=created_at.date(), end_date=WINDOW_END.date()
        )
        end_date = fake.date_between(start_date=start_date, end_date=WINDOW_END.date())
        discount_type = random.choice(DISCOUNT_TYPES)
        discount_value = (
            random.choice(PERCENTAGE_DISCOUNTS)
            if discount_type == "percentage"
            else random.choice(fixed_discounts)
        )
        promotions.append(
            {
                "promotion_code": f"PRO-{position:05d}",
                "promotion_name": fake.catch_phrase(),
                "promotion_type": random.choice(PROMOTION_TYPES),
                "discount_type": discount_type,
                "discount_value": discount_value,
                "start_date": start_date,
                "end_date": end_date,
                "created_at": created_at,
                "created_by": CREATED_BY,
                "updated_at": None,
                "updated_by": None,
                "deleted_at": None,
                "deleted_by": None,
                "is_deleted": False,
                "loaded_at": None,
            }
        )
    return promotions


def generate_promotion_products(
    fake: Faker, promotions: list[Record], products: list[Record]
) -> list[Record]:
    """Generate unique, temporally valid links between campaigns and products."""

    assert promotions, "Promotions are required before promotion-product mappings"
    assert products, "Products are required before promotion-product mappings"
    candidate_pools = [
        (promotion_id, promotion, _eligible_products_for_promotion(promotion, products))
        for promotion_id, promotion in enumerate(promotions, start=1)
    ]
    if sum(len(candidates) for _, _, candidates in candidate_pools) < PROMOTION_PRODUCT_COUNT:
        raise ValueError("Unable to generate 500 valid promotion-product pairs")

    mappings: list[Record] = []

    while len(mappings) < PROMOTION_PRODUCT_COUNT:
        available_pools = [pool for pool in candidate_pools if pool[2]]
        if not available_pools:
            raise ValueError("Unable to generate 500 valid promotion-product pairs")
        promotion_id, promotion, eligible_products = random.choice(available_pools)
        product_id, product = eligible_products.pop(random.randrange(len(eligible_products)))
        earliest_created_at = max(promotion["created_at"], product["created_at"])
        latest_created_at = datetime.combine(promotion["end_date"], datetime.max.time())
        assert earliest_created_at <= latest_created_at, (
            "A promotion-product mapping has no valid creation time"
        )
        mappings.append(
            {
                "promotion_id": promotion_id,
                "promotion_product_code": f"PPM-{len(mappings) + 1:06d}",
                "product_id": product_id,
                "created_at": fake.date_time_between(
                    start_date=earliest_created_at, end_date=latest_created_at
                ),
                "created_by": CREATED_BY,
                "updated_at": None,
                "updated_by": None,
                "deleted_at": None,
                "deleted_by": None,
                "is_deleted": False,
                "loaded_at": None,
            }
        )

    return mappings


def _eligible_products_for_promotion(
    promotion: Record,
    products: list[Record],
) -> list[tuple[int, Record]]:
    """Return unmapped products that meet the campaign's date and price rules."""

    campaign_start_end = datetime.combine(promotion["start_date"], datetime.max.time())
    return [
        (product_id, product)
        for product_id, product in enumerate(products, start=1)
        if product["created_at"] <= campaign_start_end
        and (
            promotion["discount_type"] == "percentage"
            or product["price"] >= promotion["discount_value"]
        )
    ]
