"""Validation rules for the complete in-memory synthetic dataset."""

from datetime import datetime
from decimal import Decimal

from ecommerce_oltp_system.constants import (
    BRAND_COUNT,
    CREATED_BY,
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


def _validate_unique_field(records: list[Record], field: str) -> None:
    values = [record[field] for record in records]
    assert len(values) == len(set(values)), f"{field} values must be unique"


def _validate_audit_fields(records: list[Record]) -> None:
    for record in records:
        assert record["created_by"] == CREATED_BY
        assert record["updated_at"] is None
        assert record["updated_by"] is None
        assert record["deleted_at"] is None
        assert record["deleted_by"] is None
        assert record["is_deleted"] is False
        assert record["loaded_at"] is None


def validate_brands(brands: list[Record]) -> None:
    assert len(brands) == BRAND_COUNT, "Expected 20 brands"
    _validate_unique_field(brands, "brand_code")
    _validate_audit_fields(brands)
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
    _validate_unique_field(categories, "category_code")
    _validate_audit_fields(categories)
    assert len({category["category_name"] for category in categories}) == len(categories), (
        "Category names must be unique"
    )

    main_categories = [category for category in categories if category["level"] == 1]
    subcategories = [category for category in categories if category["level"] == 2]
    assert len(main_categories) == MAIN_CATEGORY_COUNT, "Expected 5 main categories"
    assert len(subcategories) == SUBCATEGORY_COUNT, "Expected 20 sub-categories"
    assert all(category["level"] == 1 for category in categories[:MAIN_CATEGORY_COUNT])
    assert all(category["level"] == 2 for category in categories[MAIN_CATEGORY_COUNT:])
    main_category_ids = set(range(1, MAIN_CATEGORY_COUNT + 1))

    for category in categories:
        assert WINDOW_START <= category["created_at"] <= WINDOW_END, (
            "Category created_at is outside the generation window"
        )
        if category["level"] == 1:
            assert category["parent_category_id"] is None, (
                "A level-1 category cannot have a parent"
            )
        else:
            assert category["parent_category_id"] in main_category_ids
            parent = categories[category["parent_category_id"] - 1]
            assert parent["level"] == 1, "A sub-category parent must be level 1"
            assert parent["created_at"] <= category["created_at"], (
                "A parent category cannot be newer than its child"
            )


def validate_sellers(sellers: list[Record]) -> None:
    assert len(sellers) == SELLER_COUNT, "Expected 50 sellers"
    _validate_unique_field(sellers, "seller_code")
    _validate_audit_fields(sellers)
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
    _validate_unique_field(products, "product_code")
    _validate_audit_fields(products)
    valid_category_ids = set(range(MAIN_CATEGORY_COUNT + 1, len(categories) + 1))

    for product in products:
        assert 1 <= product["brand_id"] <= BRAND_COUNT, "Invalid brand_id"
        assert product["category_id"] in valid_category_ids, "Invalid category_id"
        assert 1 <= product["seller_id"] <= SELLER_COUNT, "Invalid seller_id"
        brand = brands[product["brand_id"] - 1]
        category = categories[product["category_id"] - 1]
        seller = sellers[product["seller_id"] - 1]
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
    _validate_audit_fields(customers)
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
    _validate_unique_field(promotions, "promotion_code")
    _validate_audit_fields(promotions)
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
    _validate_audit_fields(promotion_products)
    used_pairs: set[tuple[int, int]] = set()

    for mapping in promotion_products:
        assert 1 <= mapping["promotion_id"] <= PROMOTION_COUNT
        assert 1 <= mapping["product_id"] <= PRODUCT_COUNT
        pair = (mapping["promotion_id"], mapping["product_id"])
        assert pair not in used_pairs, "Promotion-product pairs must be unique"
        used_pairs.add(pair)

        promotion = promotions[mapping["promotion_id"] - 1]
        product = products[mapping["product_id"] - 1]

        campaign_start_end = datetime.combine(
            promotion["start_date"], datetime.max.time()
        )
        campaign_end = datetime.combine(promotion["end_date"], datetime.max.time())
        assert product["created_at"] <= campaign_start_end
        assert promotion["created_at"] <= mapping["created_at"]
        assert product["created_at"] <= mapping["created_at"]
        assert mapping["created_at"] <= campaign_end

        if promotion["discount_type"] == "percentage":
            discount_amount = (
                product["price"] * promotion["discount_value"] / Decimal("100")
            )
            final_price = product["price"] - discount_amount
            assert discount_amount <= product["price"]
        else:
            final_price = product["price"] - promotion["discount_value"]
            assert promotion["discount_value"] <= product["price"]
        assert final_price >= 0, "Promotion creates a negative product price"
