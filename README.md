## Synthetic-data generator (first version)

This version generates and validates `brand`, `category`, `seller`, `product`,
`customer`, `promotion`, and `promotion_product`. It has no database loader
yet: records stay in memory until all validation checks succeed, so a failed run
has no partial output to resume.

Run one deterministic session:

```bash
uv run ecommerce-oltp-system
```

Run the tests:

```bash
uv run python -m unittest discover -s tests
```

The generator uses seed `42` by default. It creates brands, sellers, main and
sub-categories, then products; customers are independent. Promotions are
generated after products, and promotion-product mappings use only compatible
products with real generated FK values. Each mapping is unique, is added only
after its product and promotion exist, and preserves the base product price.
Products are created no earlier than their brand, category, seller join date,
and seller `created_at`. Product IDs model the IDs a fresh `SERIAL` database
load would assign.
