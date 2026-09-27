"""Static table metadata and CSV type mappings for the loader."""

from .models import LargeTableLoad, TableLoad


AUDIT_COLUMNS = (
    "created_at",
    "created_by",
    "updated_at",
    "updated_by",
    "deleted_at",
    "deleted_by",
    "is_deleted",
)

UPSERT_BATCH_SIZE = 10_000
"""Rows passed to one ``execute_values`` call for small and medium tables."""

PART_LOAD_ATTEMPTS = 2
"""Attempts for an order or order-item part after a rolled-back failure."""

ORDER_LOAD = LargeTableLoad(
    table="order",
    staging_table="staging_order",
    primary_key="order_id",
    columns=(
        "customer_id", "order_code", "order_date", "status", "total_amount",
        *AUDIT_COLUMNS, "loaded_at",
    ),
    conflict_columns=("order_code",),
    validate_order_ids=True,
)

ORDER_ITEM_LOAD = LargeTableLoad(
    table="order_item",
    staging_table="staging_order_item",
    primary_key="order_item_id",
    columns=(
        "order_id", "order_item_code", "product_id", "order_date", "quantity",
        "unit_price", "subtotal", *AUDIT_COLUMNS, "loaded_at",
    ),
    conflict_columns=("order_item_code",),
)

TABLE_LOADS = (
    TableLoad("brand", "brand_id", ("brand_code", "brand_name", "country", *AUDIT_COLUMNS), ("brand_code",), True),
    TableLoad("category", "category_id", ("category_code", "category_name", "parent_category_id", "level", *AUDIT_COLUMNS), ("category_code",), True),
    TableLoad("seller", "seller_id", ("seller_code", "seller_name", "join_date", "created_at", "seller_type", "rating", "country", "created_by", "updated_at", "updated_by", "deleted_at", "deleted_by", "is_deleted"), ("seller_code",), True),
    TableLoad("customer", "customer_id", ("customer_code", "customer_name", "email", "phone", "gender", "address", "city", *AUDIT_COLUMNS), ("customer_code",), True),
    TableLoad("product", "product_id", ("product_code", "product_name", "category_id", "brand_id", "seller_id", "price", "stock_qty", "rating", "created_at", "is_active", "created_by", "updated_at", "updated_by", "deleted_at", "deleted_by", "is_deleted"), ("product_code",), True),
    TableLoad("promotion", "promotion_id", ("promotion_code", "promotion_name", "promotion_type", "discount_type", "discount_value", "start_date", "end_date", *AUDIT_COLUMNS), ("promotion_code",), True),
    TableLoad("promotion_product", "promo_product_id", ("promotion_id", "promotion_product_code", "product_id", *AUDIT_COLUMNS), ("promotion_product_code",)),
)

INTEGER_COLUMNS = {"parent_category_id", "level", "category_id", "brand_id", "seller_id", "stock_qty", "promotion_id", "product_id"}
DECIMAL_COLUMNS = {"rating", "price", "discount_value"}
DATE_COLUMNS = {"join_date", "start_date", "end_date"}
TIMESTAMP_COLUMNS = {"created_at", "updated_at", "deleted_at"}
BOOLEAN_COLUMNS = {"is_active", "is_deleted"}
