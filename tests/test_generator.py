import unittest
from hashlib import sha256
from datetime import timedelta

from ecommerce_oltp_system.generator import (
    CUSTOMER_COUNT,
    PRODUCT_COUNT,
    PROMOTION_COUNT,
    PROMOTION_PRODUCT_COUNT,
    SEED,
    generate_data,
    validate_brands,
    validate_categories,
    validate_customers,
    validate_promotion_products,
    validate_promotions,
    validate_products,
    validate_sellers,
)


class GeneratorTests(unittest.TestCase):
    def test_generation_meets_all_validation_rules(self) -> None:
        data = generate_data()

        validate_brands(data.brands)
        validate_categories(data.categories)
        validate_sellers(data.sellers)
        validate_products(data.products, data.brands, data.categories, data.sellers)
        validate_customers(data.customers)
        validate_promotions(data.promotions)
        validate_promotion_products(
            data.promotion_products, data.promotions, data.products
        )
        self.assertEqual(len(data.products), PRODUCT_COUNT)
        self.assertEqual(len(data.customers), CUSTOMER_COUNT)
        self.assertEqual(len(data.promotions), PROMOTION_COUNT)
        self.assertEqual(len(data.promotion_products), PROMOTION_PRODUCT_COUNT)

    def test_same_seed_generates_identical_data(self) -> None:
        first_run = generate_data(SEED)
        second_run = generate_data(SEED)

        self.assertEqual(_dataset_fingerprint(first_run), _dataset_fingerprint(second_run))

    def test_a_different_seed_changes_the_generated_data(self) -> None:
        self.assertNotEqual(
            _dataset_fingerprint(generate_data(SEED)),
            _dataset_fingerprint(generate_data(SEED + 1)),
        )

    def test_product_cannot_predate_seller_record(self) -> None:
        data = generate_data()
        product = data.products[0]
        seller = data.sellers[product["seller_id"] - 1]
        seller["created_at"] = product["created_at"] + timedelta(seconds=1)

        with self.assertRaisesRegex(AssertionError, "Product predates its seller record"):
            validate_products(
                data.products, data.brands, data.categories, data.sellers
            )

    def test_records_do_not_include_database_primary_keys(self) -> None:
        data = generate_data()
        tables = (
            (data.brands, "brand_id"),
            (data.categories, "category_id"),
            (data.sellers, "seller_id"),
            (data.products, "product_id"),
            (data.customers, "customer_id"),
            (data.promotions, "promotion_id"),
            (data.promotion_products, "promo_product_id"),
        )

        for records, primary_key in tables:
            self.assertTrue(all(primary_key not in record for record in records))


def _dataset_fingerprint(data: object) -> str:
    """Compare generated values and references without database primary keys."""

    dataset = data
    values = (
        tuple(_record_values(record) for record in dataset.brands),
        tuple(_record_values(record) for record in dataset.categories),
        tuple(_record_values(record) for record in dataset.sellers),
        tuple(_record_values(record) for record in dataset.products),
        tuple(_record_values(record) for record in dataset.customers),
        tuple(_record_values(record) for record in dataset.promotions),
        tuple(_record_values(record) for record in dataset.promotion_products),
    )
    return sha256(repr(values).encode()).hexdigest()


def _record_values(record: dict) -> tuple:
    return tuple(sorted(record.items()))


if __name__ == "__main__":
    unittest.main()
