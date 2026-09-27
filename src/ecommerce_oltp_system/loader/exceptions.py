"""Domain-specific failures reported by the PostgreSQL loader."""


class TableLoadError(RuntimeError):
    """Raised when a complete CSV or part-file transaction is rolled back."""


class CheckpointMismatchError(RuntimeError):
    """Raised when a completed file name refers to changed source contents."""
