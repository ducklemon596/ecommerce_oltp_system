"""Validation rules for the complete in-memory synthetic dataset."""

from datetime import datetime
from decimal import Decimal

from ecommerce_oltp_system.constants import (
    BRAND_COUNT,
    CUSTOMER_COUNT,
    DISCOUNT_TYPES,
    GENDERS,
    MAIN_CATEGORY_COUNT,
    PRODUCT_COUNT,
    PROMOTION_COUNT,
    PROMOTION_PRODUCT_COUNT,
    PROMOTION_TYPES,
    SELLER_COUNT,
    SELLER_TYPES,
    SUBCATEGORY_COUNT,
    WINDOW_END,
    WINDOW_START,
)
from ecommerce_oltp_system.models import Record


def _is_generated_reference(record: Record | None, records: list[Record]) -> bool:
    """Check that a relationship points to a generated in-memory record."""

    return any(record is candidate for candidate in records)


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

    main_categories = [category for category in categories if category["level"] == 1]
    subcategories = [category for category in categories if category["level"] == 2]
    assert len(main_categories) == MAIN_CATEGORY_COUNT, "Expected 5 main categories"
    assert len(subcategories) == SUBCATEGORY_COUNT, "Expected 20 sub-categories"

    for category in categories:
        assert WINDOW_START <= category["created_at"] <= WINDOW_END, (
            "Category created_at is outside the generation window"
        )
        if category["level"] == 1:
            assert category["parent_category_ref"] is None, (
                "A level-1 category cannot have a parent"
            )
        else:
            parent = category["parent_category_ref"]
            assert _is_generated_reference(parent, categories), (
                "A sub-category must reference a generated parent"
            )
            assert parent is not None
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
        assert WINDOW_START <= seller["created_at"] <= WINDOW_END, (
            "Seller created_at is outside the generation window"
        )


def validate_products(
    products: list[Record],
    brands: list[Record],
    categories: list[Record],
    sellers: list[Record],
) -> None:
    assert len(products) == PRODUCT_COUNT, "Expected 3,000 products"

    for product in products:
        brand = product["brand_ref"]
        category = product["category_ref"]
        seller = product["seller_ref"]
        assert _is_generated_reference(brand, brands), (
            "Product must reference a generated brand"
        )
        assert _is_generated_reference(category, categories), (
            "Product must reference a generated category"
        )
        assert _is_generated_reference(seller, sellers), (
            "Product must reference a generated seller"
        )
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
        assert seller["created_at"] <= product["created_at"], (
            "Product predates its seller record"
        )


def validate_customers(customers: list[Record]) -> None:
    assert len(customers) == CUSTOMER_COUNT, "Expected 30,000 customers"
    assert len({customer["email"] for customer in customers}) == CUSTOMER_COUNT, (
        "Customer emails must be unique"
    )
    assert len({customer["phone"] for customer in customers}) == CUSTOMER_COUNT, (
        "Customer phone numbers must be unique"
    )
    for customer in customers:
        assert customer["gender"] in GENDERS, "Invalid customer gender"
        assert WINDOW_START <= customer["created_at"] <= WINDOW_END, (
            "Customer created_at is outside the generation window"
        )


def validate_promotions(promotions: list[Record]) -> None:
    assert len(promotions) == PROMOTION_COUNT, "Expected 30 promotions"
    for promotion in promotions:
        assert promotion["promotion_type"] in PROMOTION_TYPES, "Invalid promotion type"
        assert promotion["discount_type"] in DISCOUNT_TYPES, "Invalid discount type"
        assert WINDOW_START <= promotion["created_at"] <= WINDOW_END, (
            "Promotion created_at is outside the generation window"
        )
        assert promotion["created_at"].date() <= promotion["start_date"], (
            "Promotion starts before it is created"
        )
        assert promotion["start_date"] <= promotion["end_date"], (
            "Promotion ends before it starts"
        )
        assert promotion["end_date"] <= WINDOW_END.date(), (
            "Promotion ends outside the generation window"
        )
        assert promotion["discount_value"] > 0, "Promotion discount must be positive"
        if promotion["discount_type"] == "percentage":
            assert promotion["discount_value"] <= 100, (
                "Percentage discounts cannot exceed 100%"
            )


def validate_promotion_products(
    promotion_products: list[Record], promotions: list[Record], products: list[Record]
) -> None:
    assert len(promotion_products) == PROMOTION_PRODUCT_COUNT, (
        "Expected 500 promotion-product mappings"
    )
    used_pairs: list[tuple[Record, Record]] = []

    for mapping in promotion_products:
        promotion = mapping["promotion_ref"]
        product = mapping["product_ref"]
        assert _is_generated_reference(promotion, promotions), (
            "Promotion-product mapping must reference a generated promotion"
        )
        assert _is_generated_reference(product, products), (
            "Promotion-product mapping must reference a generated product"
        )
        assert not any(
            used_promotion is promotion and used_product is product
            for used_promotion, used_product in used_pairs
        ), "Promotion-product pairs must be unique"
        used_pairs.append((promotion, product))

        campaign_start_end = datetime.combine(
            promotion["start_date"], datetime.max.time()
        )
        campaign_end = datetime.combine(promotion["end_date"], datetime.max.time())
        assert product["created_at"] <= campaign_start_end, (
            "Mapped product must exist by the campaign start"
        )
        assert promotion["created_at"] <= mapping["created_at"], (
            "Promotion-product mapping predates its promotion"
        )
        assert product["created_at"] <= mapping["created_at"], (
            "Promotion-product mapping predates its product"
        )
        assert mapping["created_at"] <= campaign_end, (
            "Promotion-product mapping is after the campaign end"
        )

        if promotion["discount_type"] == "percentage":
            discount_amount = (
                product["price"] * promotion["discount_value"] / Decimal("100")
            )
            final_price = product["price"] - discount_amount
            assert discount_amount <= product["price"], (
                "Percentage discount exceeds the product price"
            )
        else:
            final_price = product["price"] - promotion["discount_value"]
            assert promotion["discount_value"] <= product["price"], (
                "Fixed discount exceeds the product price"
            )
        assert final_price >= 0, "Promotion creates a negative product price"
