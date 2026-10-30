"""Connection policy shared by tests, with strict failures for CI."""

import os
import unittest
from pathlib import Path

import psycopg2

from ecommerce_oltp_system.loader.db.connection import database_config


def test_settings(*, explicit: bool = False) -> dict[str, str]:
    """Resolve the dedicated INI; strict runs never turn missing DBs into skips."""
    config = os.environ.get("ECOMMERCE_TEST_CONFIG")
    if (explicit or os.environ.get("ECOMMERCE_TEST_STRICT") == "1") and not config:
        unavailable("Set ECOMMERCE_TEST_CONFIG to a dedicated test INI.")
    try:
        return database_config(Path(config or "database.ini"))
    except (OSError, ValueError) as error:
        unavailable(str(error))


def unavailable(message: str) -> None:
    """Local optional tests skip; ECOMMERCE_TEST_STRICT=1 fails instead."""
    if os.environ.get("ECOMMERCE_TEST_STRICT") == "1":
        raise AssertionError(f"Required test PostgreSQL unavailable: {message}")
    raise unittest.SkipTest(f"PostgreSQL unavailable: {message}")


def connect_test_database(settings: dict[str, str]):
    """Connect without swallowing authentication or availability failures in CI."""
    try:
        return psycopg2.connect(**settings)
    except psycopg2.OperationalError as error:
        unavailable(str(error))
