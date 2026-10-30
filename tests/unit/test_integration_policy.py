"""CI must fail when real PostgreSQL verification cannot run."""

import os
import unittest
from unittest.mock import patch

import psycopg2

from tests.integration_support import connect_test_database, test_settings


class IntegrationPolicyTests(unittest.TestCase):
    def test_strict_mode_requires_explicit_config(self):
        with patch.dict(os.environ, {"ECOMMERCE_TEST_STRICT": "1"}, clear=True):
            with self.assertRaisesRegex(AssertionError, "Set ECOMMERCE_TEST_CONFIG"):
                test_settings()

    def test_strict_mode_never_skips_unavailable_postgresql(self):
        with patch.dict(os.environ, {"ECOMMERCE_TEST_STRICT": "1"}, clear=True), \
             patch("psycopg2.connect", side_effect=psycopg2.OperationalError("unavailable")):
            with self.assertRaisesRegex(AssertionError, "Required test PostgreSQL unavailable"):
                connect_test_database({})

    def test_optional_local_connection_failure_is_explicit_skip(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch("psycopg2.connect", side_effect=psycopg2.OperationalError("unavailable")):
            with self.assertRaisesRegex(unittest.SkipTest, "PostgreSQL unavailable"):
                connect_test_database({})
