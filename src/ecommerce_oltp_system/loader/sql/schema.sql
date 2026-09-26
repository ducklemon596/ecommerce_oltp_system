CREATE TABLE IF NOT EXISTS brand (
    brand_id SERIAL PRIMARY KEY,
    brand_code VARCHAR(20) NOT NULL UNIQUE,
    brand_name TEXT NOT NULL UNIQUE,
    country TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    created_by TEXT NOT NULL,
    updated_at TIMESTAMP NULL,
    updated_by TEXT NULL,
    deleted_at TIMESTAMP NULL,
    deleted_by TEXT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS category (
    category_id SERIAL PRIMARY KEY,
    category_code VARCHAR(20) NOT NULL UNIQUE,
    category_name TEXT NOT NULL UNIQUE,
    parent_category_id INTEGER NULL REFERENCES category (category_id),
    level SMALLINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    created_by TEXT NOT NULL,
    updated_at TIMESTAMP NULL,
    updated_by TEXT NULL,
    deleted_at TIMESTAMP NULL,
    deleted_by TEXT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT category_level_check CHECK (level IN (1, 2)),
    CONSTRAINT category_parent_check CHECK (
        (level = 1 AND parent_category_id IS NULL)
        OR (level = 2 AND parent_category_id IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS seller (
    seller_id SERIAL PRIMARY KEY,
    seller_code VARCHAR(20) NOT NULL UNIQUE,
    seller_name TEXT NOT NULL,
    join_date DATE NOT NULL,
    created_at TIMESTAMP NOT NULL,
    seller_type TEXT NOT NULL,
    rating NUMERIC(2, 1) NOT NULL,
    country TEXT NOT NULL,
    created_by TEXT NOT NULL,
    updated_at TIMESTAMP NULL,
    updated_by TEXT NULL,
    deleted_at TIMESTAMP NULL,
    deleted_by TEXT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT seller_type_check CHECK (seller_type IN ('Official', 'Marketplace')),
    CONSTRAINT seller_rating_check CHECK (rating BETWEEN 0 AND 5),
    CONSTRAINT seller_country_check CHECK (country = 'Vietnam')
);

CREATE TABLE IF NOT EXISTS customer (
    customer_id SERIAL PRIMARY KEY,
    customer_code VARCHAR(20) NOT NULL UNIQUE,
    customer_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT NOT NULL UNIQUE,
    gender TEXT NOT NULL,
    address TEXT NOT NULL,
    city TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    created_by TEXT NOT NULL,
    updated_at TIMESTAMP NULL,
    updated_by TEXT NULL,
    deleted_at TIMESTAMP NULL,
    deleted_by TEXT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT customer_gender_check CHECK (gender IN ('Male', 'Female'))
);

CREATE TABLE IF NOT EXISTS product (
    product_id SERIAL PRIMARY KEY,
    product_code VARCHAR(20) NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES category (category_id),
    brand_id INTEGER NOT NULL REFERENCES brand (brand_id),
    seller_id INTEGER NOT NULL REFERENCES seller (seller_id),
    price NUMERIC(14, 2) NOT NULL,
    stock_qty INTEGER NOT NULL,
    rating NUMERIC(2, 1) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    is_active BOOLEAN NOT NULL,
    created_by TEXT NOT NULL,
    updated_at TIMESTAMP NULL,
    updated_by TEXT NULL,
    deleted_at TIMESTAMP NULL,
    deleted_by TEXT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT product_price_check CHECK (price > 0),
    CONSTRAINT product_stock_check CHECK (stock_qty >= 0),
    CONSTRAINT product_rating_check CHECK (rating BETWEEN 0 AND 5)
);

CREATE TABLE IF NOT EXISTS promotion (
    promotion_id SERIAL PRIMARY KEY,
    promotion_code VARCHAR(20) NOT NULL UNIQUE,
    promotion_name TEXT NOT NULL,
    promotion_type TEXT NOT NULL,
    discount_type TEXT NOT NULL,
    discount_value NUMERIC(14, 2) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    created_at TIMESTAMP NOT NULL,
    created_by TEXT NOT NULL,
    updated_at TIMESTAMP NULL,
    updated_by TEXT NULL,
    deleted_at TIMESTAMP NULL,
    deleted_by TEXT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT promotion_type_check CHECK (promotion_type IN ('product', 'flash_sale')),
    CONSTRAINT promotion_discount_type_check CHECK (
        discount_type IN ('percentage', 'fixed_amount')
    ),
    CONSTRAINT promotion_discount_value_check CHECK (
        discount_value > 0
        AND (discount_type <> 'percentage' OR discount_value <= 100)
    ),
    CONSTRAINT promotion_dates_check CHECK (start_date <= end_date),
    CONSTRAINT promotion_created_check CHECK (created_at::date <= start_date)
);

CREATE TABLE IF NOT EXISTS promotion_product (
    promo_product_id SERIAL PRIMARY KEY,
    promotion_product_code VARCHAR(20) NOT NULL UNIQUE,
    promotion_id INTEGER NOT NULL REFERENCES promotion (promotion_id),
    product_id INTEGER NOT NULL REFERENCES product (product_id),
    created_at TIMESTAMP NOT NULL,
    created_by TEXT NOT NULL,
    updated_at TIMESTAMP NULL,
    updated_by TEXT NULL,
    deleted_at TIMESTAMP NULL,
    deleted_by TEXT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT promotion_product_unique UNIQUE (promotion_id, product_id)
);


CREATE TABLE IF NOT EXISTS "order" (
    order_id SERIAL PRIMARY KEY,
    order_code VARCHAR(20) NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL REFERENCES customer (customer_id),
    order_date TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    created_by TEXT NOT NULL,
    updated_at TIMESTAMP NULL,
    updated_by TEXT NULL,
    deleted_at TIMESTAMP NULL,
    deleted_by TEXT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT order_status_check CHECK (
        status IN ('PLACED', 'PAID', 'SHIPPED', 'DELIVERED', 'CANCELLED', 'RETURNED')
    ),
    CONSTRAINT order_total_check CHECK (total_amount >= 0),
    CONSTRAINT order_created_check CHECK (created_at >= order_date)
);

CREATE TABLE IF NOT EXISTS order_item (
    order_item_id BIGSERIAL PRIMARY KEY,
    order_item_code VARCHAR(20) NOT NULL UNIQUE,
    order_id INTEGER NOT NULL REFERENCES "order" (order_id),
    product_id INTEGER NOT NULL REFERENCES product (product_id),
    order_date TIMESTAMP NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    subtotal DECIMAL(12, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    created_by TEXT NOT NULL,
    updated_at TIMESTAMP NULL,
    updated_by TEXT NULL,
    deleted_at TIMESTAMP NULL,
    deleted_by TEXT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT order_item_source_unique UNIQUE (order_id, product_id),
    CONSTRAINT order_item_quantity_check CHECK (quantity > 0),
    CONSTRAINT order_item_price_check CHECK (unit_price > 0),
    CONSTRAINT order_item_subtotal_check CHECK (subtotal = quantity * unit_price),
    CONSTRAINT order_item_created_check CHECK (created_at >= order_date)
);

CREATE UNLOGGED TABLE IF NOT EXISTS staging_order (
    staging_row_id BIGINT GENERATED ALWAYS AS IDENTITY,
    order_code VARCHAR(20),
    customer_id INTEGER,
    order_date TIMESTAMP,
    status VARCHAR(20),
    total_amount DECIMAL(12, 2),
    created_at TIMESTAMP,
    created_by TEXT,
    updated_at TIMESTAMP,
    updated_by TEXT,
    deleted_at TIMESTAMP,
    deleted_by TEXT,
    is_deleted BOOLEAN,
    loaded_at TIMESTAMP
);

CREATE UNLOGGED TABLE IF NOT EXISTS staging_order_item (
    staging_row_id BIGINT GENERATED ALWAYS AS IDENTITY,
    order_id INTEGER,
    order_item_code VARCHAR(20),
    product_id INTEGER,
    order_date TIMESTAMP,
    quantity INTEGER,
    unit_price DECIMAL(12, 2),
    subtotal DECIMAL(12, 2),
    created_at TIMESTAMP,
    created_by TEXT,
    updated_at TIMESTAMP,
    updated_by TEXT,
    deleted_at TIMESTAMP,
    deleted_by TEXT,
    is_deleted BOOLEAN,
    loaded_at TIMESTAMP
);

