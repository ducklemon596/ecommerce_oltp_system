"""PostgreSQL connection configuration for the loader entry point."""

from __future__ import annotations

import configparser
from pathlib import Path


def database_config(config_path: str | Path, section: str = "postgresql") -> dict[str, str]:
    """Read connection settings for the loader CLI before schema/load stages.

    ``config_path`` and ``section`` identify a PostgreSQL INI configuration.
    The returned mapping is passed unchanged to ``psycopg2.connect`` by the
    loader pipeline; this function performs no database connection or mutation.
    """
    parser = configparser.ConfigParser(interpolation=None)
    try:
        found = parser.read(config_path)
    except configparser.Error as error:
        raise ValueError(f"Invalid database configuration: {config_path}. Check its INI syntax.") from error
    if not found:
        raise FileNotFoundError(f"Database configuration file not found: {config_path}")
    if not parser.has_section(section):
        raise ValueError(f"Database configuration section [{section}] is missing from {config_path}")
    settings = dict(parser.items(section))
    missing = sorted({"host", "database", "user", "password"} - settings.keys())
    if missing:
        raise ValueError(f"Database configuration section [{section}] is missing: {', '.join(missing)}")
    return settings
