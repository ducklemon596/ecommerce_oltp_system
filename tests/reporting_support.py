"""Read the current SQL catalog for standalone/function contract tests.

Standalone examples use fixed literals and omit parameter-dependent branches.
Database integration tests compare their values, ordering, and columns with the
parameterized functions; this module only reads signatures and sample inputs.
"""

import re
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTING = ROOT / "database/reporting"
EXAMPLE_PARAMETERS = {
    "p_start_date": date(2025, 1, 1),
    "p_end_date": date(2025, 6, 1),
    "p_product_ids": [1, 2],
    "p_seller_ids": [1, 2],
    "p_category_ids": [1, 2],
    "p_brand_ids": [1, 2],
}
TOP_N = {
    "report_top_products_per_brand": 5,
    "report_highest_value_orders": 1,
    "report_top_products": 20,
}


def function_definitions() -> dict[str, tuple[str, str, str]]:
    """Return signature, output-column declaration, and body in catalog order.

    This intentionally understands only this repository's SQL-language function
    format, not arbitrary PostgreSQL syntax.
    """
    pattern = (
        r"CREATE OR REPLACE FUNCTION (report_\w+)\((.*?)\)\s*"
        r"RETURNS TABLE \((.*?)\)\s*LANGUAGE SQL STABLE PARALLEL SAFE\s*"
        r"AS \$\$(.*?)\$\$;"
    )
    return {name: (args, columns, body.strip()) for name, args, columns, body in
            re.findall(pattern, (REPORTING / "functions.sql").read_text(), re.S)}


def example_parameters(name: str, signature: str) -> dict:
    """Return typed, explicitly documented sample arguments for one report."""
    names = re.findall(r"\b(p_\w+)\s+(?:DATE|INTEGER(?:\[\])?)", signature)
    return {key: TOP_N[name] if key == "p_top_n" else EXAMPLE_PARAMETERS[key] for key in names}


def sql_literal(value) -> str:
    """Render trusted fixture dates, ID lists, or limits as pgAdmin-ready literals."""
    if isinstance(value, date):
        return f"DATE '{value.isoformat()}'"
    if isinstance(value, list):
        return f"ARRAY[{', '.join(str(item) for item in value)}]::INTEGER[]"
    return str(value)


def render_example(body: str, parameters: dict) -> str:
    """Substitute whole parameter identifiers, leaving joins/aggregations untouched."""
    return re.sub(r"\bp_\w+\b", lambda match: sql_literal(parameters[match[0]]), body)


def standalone_queries() -> dict[str, str]:
    """Read labeled complete SELECT statements in their published order."""
    blocks = re.split(r"^-- Function: (report_\w+)\s*$", (REPORTING / "queries.sql").read_text(), flags=re.M)
    return {name: re.sub(r"^--[^\n]*\n", "", block, flags=re.M).strip()
            for name, block in zip(blocks[1::2], blocks[2::2])}
