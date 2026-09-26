"""Generator for independent customer records."""

import random
from typing import Callable

from faker import Faker

from ecommerce_oltp_system.shared.constants import (
    CREATED_BY,
    CUSTOMER_COUNT,
    GENDERS,
    MAX_UNIQUE_VALUE_ATTEMPTS,
    WINDOW_END,
    WINDOW_START,
)
from ecommerce_oltp_system.shared.models import Record


def generate_customers(fake: Faker) -> list[Record]:
    """Generate independent Vietnamese customer records with unique contacts."""

    used_emails: set[str] = set()
    used_phones: set[str] = set()
    customers: list[Record] = []
    for position in range(1, CUSTOMER_COUNT + 1):
        customers.append(
            {
                "customer_code": f"CUS-{position:06d}",
                "customer_name": fake.name(),
                "email": _unique_value(
                    lambda: _customer_email(fake),
                    used_emails,
                    "customer email",
                ),
                "phone": _unique_value(fake.phone_number, used_phones, "customer phone"),
                "gender": random.choice(GENDERS),
                "address": fake.address(),
                "city": fake.city(),
                "created_at": fake.date_time_between(
                    start_date=WINDOW_START, end_date=WINDOW_END
                ),
                "created_by": CREATED_BY,
                "updated_at": None,
                "updated_by": None,
                "deleted_at": None,
                "deleted_by": None,
                "is_deleted": False,
                "loaded_at": None,
            }
        )
    return customers


def _unique_value(
    value_factory: Callable[[], str], used_values: set[str], value_name: str
) -> str:
    """Generate one unique value or fail if Faker's value space is exhausted."""

    for _ in range(MAX_UNIQUE_VALUE_ATTEMPTS):
        value = value_factory()
        if value not in used_values:
            used_values.add(value)
            return value
    raise ValueError(f"Unable to generate a unique {value_name}")


def _customer_email(fake: Faker) -> str:
    """Keep a Faker email realistic while making its local part scalable and unique."""

    local_part, domain = fake.email().rsplit("@", maxsplit=1)
    unique_suffix = str(fake.uuid4()).replace("-", "")[:12]
    return f"{local_part}.{unique_suffix}@{domain}"
