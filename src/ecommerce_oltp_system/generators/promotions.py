"""Generators for promotions and promotion-product mappings."""

import random
from datetime import datetime

from faker import Faker

from ecommerce_oltp_system.shared.constants import (
    CREATED_BY,
    DISCOUNT_TYPES,
    FIXED_DISCOUNTS,
    PERCENTAGE_DISCOUNTS,
    PROMOTION_COUNT,
    PROMOTION_PRODUCT_COUNT,
    PROMOTION_TYPES,
    WINDOW_END,
    WINDOW_START,
)
from ecommerce_oltp_system.shared.models import Record


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
