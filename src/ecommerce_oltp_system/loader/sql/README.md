# Packaged schema resource

| File | Purpose |
|---|---|
| [schema.sql](schema.sql) | Canonical DDL for nine final tables, constraints, audit fields, two unlogged staging tables, and checkpoints |
| `__init__.py` | Makes the SQL resource addressable through `importlib.resources` |

[db/schema.py](../db/schema.py) reads this resource when the application initializes
or loads a database. [database/schema.sql](../../../../database/schema.sql) is a
symlink to this file, not a second DDL implementation. Edit this resource when
changing application DDL; the schema contract test checks that both paths agree.

Use `uv run ecommerce init-db` to apply it. Reporting functions and performance
indexes are deployed separately; see the [database guide](../../../../database/README.md).
