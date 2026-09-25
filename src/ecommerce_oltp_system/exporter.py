"""CSV output for validated synthetic datasets."""

import csv
from pathlib import Path

from ecommerce_oltp_system.models import GeneratedData, Record


TABLE_OUTPUTS = (
    ("brand", "brands", "brand_id"),
    ("category", "categories", "category_id"),
    ("seller", "sellers", "seller_id"),
    ("customer", "customers", "customer_id"),
    ("product", "products", "product_id"),
    ("promotion", "promotions", "promotion_id"),
    ("promotion_product", "promotion_products", "promo_product_id"),
)


def write_data_files(
    data: GeneratedData, output_dir: str | Path = "data"
) -> list[Path]:
    """Write every validated table to its own deterministic CSV file."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    written_files: list[Path] = []

    for table_name, attribute_name, primary_key in TABLE_OUTPUTS:
        records: list[Record] = getattr(data, attribute_name)
        assert records, f"Cannot write empty {table_name} dataset"
        assert primary_key not in records[0], (
            f"{table_name}.csv must not contain database-managed {primary_key}"
        )

        output_path = destination / f"{table_name}.csv"
        with output_path.open("w", encoding="utf-8", newline="") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(_csv_record(record) for record in records)
        written_files.append(output_path)

    return written_files


def _csv_record(record: Record) -> Record:
    return {field: csv_value(value) for field, value in record.items()}


def csv_value(value: object) -> object:
    """Convert an in-memory value to the project's CSV representation."""

    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return value
