# Local Setup & CLI Guide

This guide shows how to start PostgreSQL and pgAdmin, generate synthetic data, load it safely, create the recommended indexes **after ingestion**, and export reports to CSV.

> Run commands from the repository root. For a first run, use a fresh database and a small sample—not the five-million-order benchmark dataset.

## 1. Prerequisites and configuration

Install **Python 3.12+**, [uv](https://docs.astral.sh/uv/), Docker Engine, and Docker Compose. Then create your local configuration:

```bash
cp -n .env.example .env
cp -n database.ini.example database.ini
uv sync --locked
```

`cp -n` does not overwrite an existing local file. The example defaults are intended for local development only:

| Setting | Default |
|---|---|
| PostgreSQL database | `ecommerce_oltp` |
| PostgreSQL user / password | `postgres` / `postgres` |
| PostgreSQL host port | `5432` |
| pgAdmin URL | `http://localhost:5050` |
| pgAdmin login | `admin@example.com` / `admin` |

Check `.env` and match the database name, user, password, host, and **published host port** in `database.ini`. Do not commit local passwords. Changing `.env` later does **not** reset credentials inside an already initialized PostgreSQL volume.

## 2. Start Docker and connect pgAdmin

```bash
docker compose up -d --wait
docker compose ps
```

PostgreSQL and pgAdmin share the Compose network, so containers resolve the database by its **service name `db`**. From your laptop, use `localhost:<published port>` instead.

Open **[http://localhost:5050](http://localhost:5050)**, log in using pgAdmin credentials from `.env`, and choose **Register → Server**:

| pgAdmin field | Value |
|---|---|
| General → Name | `E-commerce local` (any descriptive name) |
| Connection → Host | **`db`** |
| Connection → Port | **`5432`** (internal container port) |
| Maintenance database | `ecommerce_oltp` (or your configured database) |
| Username / Password | **PostgreSQL** credentials, not the pgAdmin login |

**Do not use a container IP address:** it can change after containers are recreated.

### Protect existing databases

Compose uses persistent named volumes (historically `ecommerce_oltp_pgdata` and `ecommerce_pgadmin_data`). PostgreSQL creates the named database only on **first initialization of an empty data volume**. Do not attach one data volume to multiple running PostgreSQL containers.

If you already run PostgreSQL or manually managed `ecommerce-postgres` / `ecommerce-pgadmin` containers, check for port or volume conflicts before starting Compose. For a separate demo, configure different ports and volume names in `.env`:

```dotenv
POSTGRES_PORT=15432
PGADMIN_PORT=15050
POSTGRES_VOLUME_NAME=ecommerce_demo_pgdata
PGADMIN_VOLUME_NAME=ecommerce_demo_pgadmin
```

Also create a separate `database-demo.ini` with `port=15432` and pass `--config database-demo.ini` to database commands. This keeps the demo away from your existing data.

## 3. Generate and load sample data

The CLI uses a single memorable prefix: **`uv run ecommerce`**.

```bash
# Reproducible CSV data; use a new output directory
uv run ecommerce generate --output-dir data-demo --orders 1000 --orders-per-file 500 --seed 42

# Load first; build only the recommended C1+C2 indexes afterward
uv run ecommerce load --data-dir data-demo --indexes recommended
```

The generator creates reference tables and matching `orders/order_part_*.csv` and `order_items/order_item_part_*.csv` files. The `--orders 1000` example limits transactions, but still generates the standard reference data (including 30,000 customers and 3,000 products). Generating the same seed and settings in a **fresh** directory reproduces the dataset. Regenerating over old files can leave extra CSV parts behind.

### What happens during loading?

1. **Prepare tables** and load reference data in dependency order.
2. **Bulk `COPY`** each CSV file into staging, validate it, then transactionally **UPSERT** into OLTP tables.
3. **Commit by file** and save checksums/checkpoints so completed parts can be skipped safely on retry.
4. After successful ingestion, **install the SQL reporting functions**, then create the **recommended optional indexes**.

This is intentionally not one transaction for the entire dataset. If a later file fails, earlier committed files remain; correct the problem and **rerun the same command with unchanged inputs**. Do not edit files covered by checkpoints or delete checkpoint state to bypass a mismatch.

If loading succeeds but the final SQL/index setup fails, the data is already committed. After fixing the cause, retry only setup:

```bash
uv run ecommerce setup --indexes recommended
```

### Load/index variants

| Command | Behavior |
|---|---|
| `uv run ecommerce load --data-dir data-demo` | Load data only (legacy behavior) |
| `uv run ecommerce load --data-dir data-demo --indexes recommended` | Load, then deploy functions and C1+C2 |
| `uv run ecommerce load --data-dir data-demo --indexes none` | Load and deploy functions, no new optional indexes |
| `uv run ecommerce setup --indexes recommended` | Prepare schema/functions and install C1+C2 for an existing database |
| `uv run ecommerce setup --indexes none` | Prepare schema/functions without adding optional indexes |
| `uv run ecommerce init-db` | Create application tables and mandatory constraints/indexes only |

The `recommended` option selects **C1+C2** from the historical definitions in [`database/indexes.sql`](../../database/indexes.sql). The full file contains **seven** historical optional indexes; executing it wholesale is not the two-index recommendation. **`--indexes none` never removes existing indexes.** Setup does not drop indexes; same-name indexes are not definition-validated by `IF NOT EXISTS`.

Recommended indexes use regular `CREATE INDEX`, which can block writes during creation. Apply them on a fresh demo database or during a suitable maintenance window, not casually on a live production instance.

For a non-default connection or checkout location, see CLI help for `--config PATH`, `--section NAME`, and `--sql-dir PATH` (reporting SQL/index definitions are checkout files).

## 4. Run SQL reports and export CSV

Reports call parameterized PostgreSQL functions through read-only connections. Results are exported as UTF-8 CSV with headers; existing exports are kept and new filenames are unique.

```bash
# Discover commands
uv run ecommerce --help
uv run ecommerce report list

# Broad: periodic revenue and seller summaries
uv run ecommerce report broad --start 2025-01-01 --end 2025-06-01

# Ranking: high-value orders and top products
uv run ecommerce report ranking --start 2025-01-01 --end 2025-06-01 --top 5

# Drill-down: investigate selected sellers/categories in a date window
uv run ecommerce report drill-down --sellers 1,2 --categories 6,7 --start 2025-03-01 --end 2025-04-01
```

| Group | SQL reports included | Default CSV directory |
|---|---|---|
| **`broad`** | Monthly revenue, monthly orders, seller sales/performance, product-month revenue | `reports/results/broad/` |
| **`ranking`** | Highest-value orders, top products, top products per brand | `reports/results/ranking/` |
| **`drill-down`** | Filtered seller performance, brand rankings, seller orders, status summary | `reports/results/drill-down/` |

These groups are convenient CLI batches, **not** exact reproductions of the hypothetical business sessions used in the benchmark report. Each group invokes its included reporting functions once. Filters affect only functions that support them—for instance, `--sellers` does not apply to the seller-performance function in the same way it applies to seller orders. For exact parameter semantics, use the [reporting catalog](../../database/reporting/README.md).

More examples:

```bash
# Product-item report; cap exported rows
uv run ecommerce report items --products 1,2 --limit 1000

# Selected reports in a custom destination
uv run ecommerce report all --only monthly daily --output-dir reports/results/custom
```

- **Date windows:** `--start` is inclusive, `--end` exclusive (e.g., March uses `2025-03-01` to `2025-04-01`).
- **Top-N vs CSV cap:** `--top` changes a ranking's business limit; `--limit` caps exported rows (default 50), **not** the amount of work PostgreSQL must do to compute an aggregate.
- **Outputs:** Category exports go into `reports/results/<category>/`; specifying a category `--output-dir DIR` produces `DIR/<category>/`.
- **Empty results:** The command still writes a CSV header. Some filtered queries may return nothing on a small demo dataset.
- **Failures:** A report batch reports unsuccessful functions and exits nonzero; it does not silently treat an empty result as a failure.

## 5. Test and shut down safely

```bash
# Tests that do not require PostgreSQL
uv run python -m unittest discover -s tests/unit -v

# Inspect containers and stop without deleting data
docker compose logs db pgadmin
docker compose stop
```

`docker compose down` removes Compose containers/network but **retains named volumes**. Avoid `down --volumes` if you want to keep database and pgAdmin data.

Integration tests may create and drop schemas, so point them at a **separate test database** first:

```bash
ECOMMERCE_TEST_CONFIG=database-test.ini ECOMMERCE_TEST_STRICT=1 \
  uv run python -m unittest discover -s tests/integration -v
```

Use a dedicated local `database-test.ini`; skipped tests are not evidence of successful integration. See the [test guide](../../tests/README.md) and [recovery design](../decisions/recoverable-load.md).

## Common issues

| Problem | What to check |
|---|---|
| Docker reports a port conflict | Another PostgreSQL/pgAdmin container or local service may already be using the port; configure separate demo ports and volumes. |
| Authentication fails after editing `.env` | Existing PostgreSQL volumes retain their initial credentials; match `database.ini` to the initialized database. |
| pgAdmin cannot resolve `db` | pgAdmin must be connected to the same Compose network; a separately launched instance may not resolve that service name. |
| Database does not exist | `POSTGRES_DB` applies only during empty-volume initialization; `init-db` creates tables, not a new PostgreSQL database. |
| Reporting functions missing | Run `uv run ecommerce setup --indexes none` against the intended database. |
| Missing setup SQL files | Run from the repository checkout or supply `--sql-dir`. |
| Checkpoint validation fails | Restore the original CSV inputs or use a new isolated demo dataset; do not delete checkpoints to force a retry. |

**Next:** [Repository overview](../../README.md) · [Loader internals](../../src/ecommerce_oltp_system/loader/README.md) · [SQL performance case study](../../reports/SQL_Optimization_README.md).
