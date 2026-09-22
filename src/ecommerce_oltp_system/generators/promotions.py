"""Generators for promotions and promotion-product mappings."""

import random
from datetime import datetime

from faker import Faker

from ecommerce_oltp_system.constants import (
    DISCOUNT_TYPES,
    FIXED_DISCOUNTS,
    PERCENTAGE_DISCOUNTS,
    PROMOTION_COUNT,
    PROMOTION_PRODUCT_COUNT,
    PROMOTION_TYPES,
    WINDOW_END,
    WINDOW_START,
)
from ecommerce_oltp_system.models import Record


def generate_promotions(fake: Faker, products: list[Record]) -> list[Record]:
    """Generate campaigns whose fixed discounts can be applied to products."""

    assert products, "Products are required before promotions can be generated"
    lowest_product_price = min(product["price"] for product in products)
    fixed_discounts = [
        discount for discount in FIXED_DISCOUNTS if discount <= lowest_product_price
    ]
    assert fixed_discounts, "No valid fixed discount is compatible with products"

    promotions: list[Record] = []
    for promotion_id in range(1, PROMOTION_COUNT + 1):
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
                "promotion_id": promotion_id,
                "promotion_name": f"{fake.catch_phrase()} {promotion_id}",
                "promotion_type": random.choice(PROMOTION_TYPES),
                "discount_type": discount_type,
                "discount_value": discount_value,
                "start_date": start_date,
                "end_date": end_date,
                "created_at": created_at,
            }
        )
    return promotions


def generate_promotion_products(
    fake: Faker, promotions: list[Record], products: list[Record]
) -> list[Record]:
    """Generate unique, temporally valid links between campaigns and products."""

    assert promotions, "Promotions are required before promotion-product mappings"
    assert products, "Products are required before promotion-product mappings"
    used_pairs: set[tuple[int, int]] = set()
    mappings: list[Record] = []

    while len(mappings) < PROMOTION_PRODUCT_COUNT:
        promotion = random.choice(promotions)
        eligible_products = _eligible_products_for_promotion(
            promotion, products, used_pairs
        )
        if not eligible_products:
            if all(
                not _eligible_products_for_promotion(candidate, products, used_pairs)
                for candidate in promotions
            ):
                raise ValueError("Unable to generate 500 valid promotion-product pairs")
            continue

        product = random.choice(eligible_products)
        pair = (promotion["promotion_id"], product["product_id"])
        earliest_created_at = max(promotion["created_at"], product["created_at"])
        latest_created_at = datetime.combine(promotion["end_date"], datetime.max.time())
        assert earliest_created_at <= latest_created_at, (
            "A promotion-product mapping has no valid creation time"
        )
        mappings.append(
            {
                "promo_product_id": len(mappings) + 1,
                "promotion_id": promotion["promotion_id"],
                "product_id": product["product_id"],
                "created_at": fake.date_time_between(
                    start_date=earliest_created_at, end_date=latest_created_at
                ),
            }
        )
        used_pairs.add(pair)

    return mappings


def _eligible_products_for_promotion(
    promotion: Record, products: list[Record], used_pairs: set[tuple[int, int]]
) -> list[Record]:
    """Return unmapped products that meet the campaign's date and price rules."""

    campaign_start_end = datetime.combine(promotion["start_date"], datetime.max.time())
    return [
        product
        for product in products
        if (promotion["promotion_id"], product["product_id"]) not in used_pairs
        and product["created_at"] <= campaign_start_end
        and (
            promotion["discount_type"] == "percentage"
            or product["price"] >= promotion["discount_value"]
        )
    ]
