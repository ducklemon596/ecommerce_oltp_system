"""Root command-line entry point for PostgreSQL schema creation and loading."""

from .loader.pipeline import main


if __name__ == "__main__":
    main()
