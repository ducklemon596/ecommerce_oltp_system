# Streamed orders and order items

Generates one order and its 2–5 distinct product lines at a time, validates them,
then writes paired CSV parts without retaining the full transactional dataset.

## File overview

| File | Purpose |
|---|---|
| [generator.py](generator.py) | Loads lightweight customer/product references, selects date-eligible records, generates rows, and writes/times parts |
| [models.py](models.py) | CSV column order, customer/product references, weighted selection pools, and generation statistics |
| [validation.py](validation.py) | Timestamp eligibility, domains, positive quantities/prices, item subtotals, and order totals |

## Behavior and dependencies

Order dates span January–May 2025 in position-based time intervals. Configured
weights concentrate activity in a preferential customer/product pool. The order's
customer and all products must exist by its date. Pricing uses the referenced
product price; the streamer does not apply promotion discounts or decrement stock.

Orders omit their database primary key. Item foreign keys use a global expected
future order ID that continues across parts. Each order/item set is validated
before its rows are written; interruption can leave an incomplete part containing
valid rows and headers. This is not an atomic file-publication/resume mechanism.

## Usage

The [full pipeline](../pipeline.py) runs this stage after reference CSV generation.
To reuse existing reference files:

```bash
uv run ecommerce generate --orders-only --data-dir data --output-dir data-orders --orders 1000 --orders-per-file 500
```

See the [generator guide](../README.md) for output layout and deterministic seeding.
