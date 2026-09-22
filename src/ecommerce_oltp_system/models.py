"""In-memory record types returned by the generator."""

from dataclasses import dataclass
from typing import Any


Record = dict[str, Any]


@dataclass(frozen=True)
class GeneratedData:
    """The complete output of one generation session."""

    brands: list[Record]
    categories: list[Record]
    sellers: list[Record]
    products: list[Record]
    customers: list[Record]
    promotions: list[Record]
    promotion_products: list[Record]
