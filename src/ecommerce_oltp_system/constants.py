"""Shared configuration for deterministic synthetic data generation."""

from datetime import datetime
from decimal import Decimal


SEED = 42
WINDOW_START = datetime(2025, 1, 1, 0, 0, 0)
WINDOW_END = datetime(2025, 5, 31, 23, 59, 59)

BRAND_COUNT = 20
MAIN_CATEGORY_COUNT = 5
SUBCATEGORY_COUNT = 20
SELLER_COUNT = 50
PRODUCT_COUNT = 3_000
CUSTOMER_COUNT = 30_000
PROMOTION_COUNT = 30
PROMOTION_PRODUCT_COUNT = 500

SELLER_TYPES = ("Official", "Marketplace")
GENDERS = ("Male", "Female")
PROMOTION_TYPES = ("product", "flash_sale")
DISCOUNT_TYPES = ("percentage", "fixed_amount")
PERCENTAGE_DISCOUNTS = tuple(
    Decimal(value) for value in (5, 10, 15, 20, 25, 30, 40, 50)
)
FIXED_DISCOUNTS = tuple(
    Decimal(value) for value in (10_000, 20_000, 50_000, 75_000, 100_000)
)
MAX_UNIQUE_VALUE_ATTEMPTS = 1_000

CATEGORY_TREE = {
    "Electronics": ("Mobile Phones", "Laptops", "Audio", "Smart Home"),
    "Fashion": ("Men's Clothing", "Women's Clothing", "Shoes", "Accessories"),
    "Home & Living": ("Furniture", "Kitchenware", "Bedding", "Home Decor"),
    "Beauty & Health": ("Skincare", "Makeup", "Personal Care", "Wellness"),
    "Sports & Outdoors": ("Fitness", "Cycling", "Camping", "Sportswear"),
}
