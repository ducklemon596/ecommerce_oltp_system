import unittest

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

        self.assertEqual(first_run, second_run)

    def test_a_different_seed_changes_the_generated_data(self) -> None:
        self.assertNotEqual(generate_data(SEED), generate_data(SEED + 1))


if __name__ == "__main__":
    unittest.main()
