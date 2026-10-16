"""One uv-managed application command for generation, loading, and reporting."""

import argparse

from . import generate, reporting
from .loader import pipeline as loader


def main(argv: list[str] | None = None) -> None:
    """Dispatch parsed options without duplicating pipeline or database logic."""
    parser = argparse.ArgumentParser(description="Generate, load, and report on the e-commerce dataset.")
    commands = parser.add_subparsers(dest="command", required=True)

    generate_parser = commands.add_parser("generate", help="Generate and validate CSV files.")
    generate.configure_parser(generate_parser)
    generate_parser.set_defaults(handler=generate.run)

    init_parser = commands.add_parser("init-db", help="Create application tables if missing.")
    loader.configure_parser(init_parser, initialization_only=True)
    init_parser.set_defaults(handler=loader.run)

    load_parser = commands.add_parser("load", help="Load CSV files with transactional checkpoints.")
    loader.configure_parser(load_parser)
    load_parser.set_defaults(handler=loader.run)

    report_parser = commands.add_parser("report", help="List or execute PostgreSQL reports.")
    reporting.configure_parser(report_parser)

    args = parser.parse_args(argv)
    args.handler(args)
