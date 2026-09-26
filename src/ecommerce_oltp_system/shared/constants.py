"""Shared configuration for deterministic synthetic data generation."""

from datetime import datetime
from decimal import Decimal


SEED = 42
WINDOW_START = datetime(2025, 1, 1, 0, 0, 0)
WINDOW_END = datetime(2025, 5, 31, 23, 59, 59)
PRE_WINDOW_START = datetime(2024, 12, 1, 0, 0, 0)
PRE_WINDOW_END = datetime(2024, 12, 31, 23, 59, 59)
PRODUCT_ROLLOUT_END = datetime(2025, 4, 30, 23, 59, 59)
PRE_WINDOW_PRODUCT_SHARE = 0.85

BRAND_COUNT = 20
MAIN_CATEGORY_COUNT = 5
SUBCATEGORY_COUNT = 20
SELLER_COUNT = 50
PRODUCT_COUNT = 3_000
CUSTOMER_COUNT = 30_000
PROMOTION_COUNT = 30
PROMOTION_PRODUCT_COUNT = 500
ORDER_COUNT = 5_000_000
ORDERS_PER_FILE = 100_000
MIN_ORDER_ITEMS = 2
MAX_ORDER_ITEMS = 5
MAX_ORDER_ITEM_QUANTITY = 5
CREATED_BY = "faker_batch"

SELLER_TYPES = ("Official", "Marketplace")
GENDERS = ("Male", "Female")
PROMOTION_TYPES = ("product", "flash_sale")
DISCOUNT_TYPES = ("percentage", "fixed_amount")
ORDER_STATUSES = (
    "PLACED",
    "PAID",
    "SHIPPED",
    "DELIVERED",
    "CANCELLED",
    "RETURNED",
)
ORDER_STATUS_WEIGHTS = (
    ("PLACED", 0.02),
    ("PAID", 0.10),
    ("DELIVERED", 0.60),
    ("SHIPPED", 0.20),
    ("CANCELLED", 0.05),
    ("RETURNED", 0.03),
)
PARETO_HEAD_SHARE = 0.20
PARETO_ACTIVITY_SHARE = 0.80
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
