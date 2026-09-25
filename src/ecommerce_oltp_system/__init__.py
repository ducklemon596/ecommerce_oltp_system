"""Synthetic data generation package for the e-commerce OLTP project."""


def main() -> None:
    """Compatibility entry point for the unified generator command."""

    from .generate import main as generate_main

    generate_main()
