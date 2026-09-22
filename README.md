## Synthetic-data generator (first version)

This first version generates and validates only `brand`, `category`, `seller`,
and `product`. It has no database loader yet: records stay in memory until all
validation checks succeed, so a failed run has no partial output to resume.

Run one deterministic session:

```bash
uv run ecommerce-oltp-system
```

Run the tests:

```bash
uv run python -m unittest discover -s tests
```

The generator uses seed `42` by default. It creates the independent brands and
sellers, then main categories followed by sub-categories, and finally products.
Each product chooses FK values from generated records (rather than numeric
ranges) and its timestamp is generated no earlier than its brand, category, and
seller. Product IDs model the IDs a fresh `SERIAL` database load would assign.
