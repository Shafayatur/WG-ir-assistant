"""
Neon (Postgres) connection, schema creation, and upsert logic.

Uses plain SQLAlchemy Core (no ORM) with pandas' to_sql for simplicity -
this is a small number of tables and the tool layer (Phase 2) will mostly
issue read queries, so there's no need for an ORM layer here.
"""
from sqlalchemy import create_engine, text
import pandas as pd

from src.config import Config

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(Config.NEON_DATABASE_URL, pool_pre_ping=True)
    return _engine


CREATE_ORDERS_TABLE = """
CREATE TABLE IF NOT EXISTS orders (
    id                      INTEGER PRIMARY KEY,
    increment_id            TEXT,
    is_insurance_applied    BOOLEAN,
    base_sub_total          NUMERIC,
    base_grand_total        NUMERIC,
    returned_amount         NUMERIC,
    status                  TEXT,
    stage                   TEXT,
    is_active               BOOLEAN,
    customer_name           TEXT,
    customer_phone          TEXT,
    customer_email          TEXT,
    customer_unique_id      TEXT,
    customer_created_at     DATE,
    project_name            TEXT,
    tenure                  INTEGER,
    remark                  TEXT,
    order_created_at        DATE,
    invested_created_at     DATE,
    transaction_count       NUMERIC,
    return_count            NUMERIC,
    returned_created_at     DATE,
    close_date              DATE,
    profit_min              NUMERIC,
    profit_max              NUMERIC,
    opa_id                  NUMERIC,
    bank_attachment_date    DATE,
    bank_name               TEXT,
    bank_branch             TEXT,
    synced_at               TIMESTAMP DEFAULT now()
);
"""

# Adds columns to an orders table that already exists from before this
# schema change, without touching existing rows - safe to run repeatedly.
ALTER_ORDERS_TABLE_ADD_CONTACT_COLUMNS = """
ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_name TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_phone TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_email TEXT;
"""

# Indexes on columns filtered/sorted on frequently. At 17k rows Postgres
# is fast even unindexed, but this matters more every year as more data
# accumulates - cheap to add now, before it's a real bottleneck.
CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_orders_order_created_at ON orders (order_created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_stage ON orders (stage);
CREATE INDEX IF NOT EXISTS idx_orders_project_name ON orders (project_name);
CREATE INDEX IF NOT EXISTS idx_orders_customer_unique_id ON orders (customer_unique_id);
CREATE INDEX IF NOT EXISTS idx_orders_customer_name_trgm ON orders USING gin (customer_name gin_trgm_ops);
"""

ENABLE_TRGM_EXTENSION = "CREATE EXTENSION IF NOT EXISTS pg_trgm;"

CREATE_CF_TRACKER_TABLE = """
CREATE TABLE IF NOT EXISTS cf_tracker (
    day                 DATE PRIMARY KEY,
    registrations       NUMERIC,
    tickets_booked      NUMERIC,
    tickets_invested    NUMERIC,
    unique_investors    NUMERIC,
    new_investors       NUMERIC,
    old_investors       NUMERIC,
    investment_value    NUMERIC,
    payables            NUMERIC,
    synced_at           TIMESTAMP DEFAULT now()
);
"""

CREATE_INVESTOR_SEGMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS investor_segments (
    customer_unique_id            TEXT PRIMARY KEY,
    customer_name                  TEXT,
    total_invested                  NUMERIC,
    num_investments                  INTEGER,
    avg_investment                    NUMERIC,
    first_investment                   DATE,
    last_investment                     DATE,
    tier                                  TEXT,
    favorite_category                     TEXT,
    last_project_name                     TEXT,
    has_active_investment                 BOOLEAN,
    preferred_tenure                      INTEGER,
    days_since_last_investment            INTEGER,
    activity_status                       TEXT,
    synced_at                             TIMESTAMP DEFAULT now()
);
"""


def create_tables():
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(CREATE_ORDERS_TABLE))
        conn.execute(text(ALTER_ORDERS_TABLE_ADD_CONTACT_COLUMNS))
        conn.execute(text(CREATE_CF_TRACKER_TABLE))

    # Extension + trigram index need their own transaction so a failure
    # here (e.g. permissions) doesn't roll back the table creation above.
    try:
        with engine.begin() as conn:
            conn.execute(text(ENABLE_TRGM_EXTENSION))
            conn.execute(text(CREATE_INDEXES))
    except Exception as e:
        print(f"Note: could not create trigram index (name search will still "
              f"work, just without this speed optimization): {e}")
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_orders_order_created_at ON orders (order_created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_orders_stage ON orders (stage);
                CREATE INDEX IF NOT EXISTS idx_orders_project_name ON orders (project_name);
                CREATE INDEX IF NOT EXISTS idx_orders_customer_unique_id ON orders (customer_unique_id);
            """))

    with engine.begin() as conn:
        conn.execute(text(CREATE_INVESTOR_SEGMENTS_TABLE))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_investor_segments_tier ON investor_segments (tier);
            CREATE INDEX IF NOT EXISTS idx_investor_segments_activity ON investor_segments (activity_status);
            CREATE INDEX IF NOT EXISTS idx_investor_segments_preferred_tenure ON investor_segments (preferred_tenure);
        """))


def upsert_investor_segments(df: pd.DataFrame):
    """Full replace on every sync - segments are recomputed from scratch
    each time rather than incrementally updated, since the underlying
    per-investor aggregates (tier, favorite category, etc.) can change
    based on ANY of that investor's orders, not just new ones."""
    if df.empty:
        return 0
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM investor_segments;"))
        df.to_sql("investor_segments", conn, if_exists="append", index=False)
    return len(df)


def upsert_orders(df: pd.DataFrame):
    """Full-refresh upsert: load into a staging table, then upsert into
    orders on id. Safe to re-run - re-syncing the same data is a no-op
    beyond updating synced_at."""
    if df.empty:
        return 0
    engine = get_engine()
    with engine.begin() as conn:
        df.to_sql("orders_staging", conn, if_exists="replace", index=False)
        columns = [c for c in df.columns]
        update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c != "id")
        conn.execute(text(f"""
            INSERT INTO orders ({", ".join(columns)})
            SELECT {", ".join(columns)} FROM orders_staging
            ON CONFLICT (id) DO UPDATE SET {update_clause}, synced_at = now();
        """))
        conn.execute(text("DROP TABLE orders_staging;"))
    return len(df)


def upsert_cf_tracker(df: pd.DataFrame):
    if df.empty:
        return 0
    engine = get_engine()
    with engine.begin() as conn:
        df.to_sql("cf_tracker_staging", conn, if_exists="replace", index=False)
        columns = [c for c in df.columns]
        update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c != "day")
        conn.execute(text(f"""
            INSERT INTO cf_tracker ({", ".join(columns)})
            SELECT {", ".join(columns)} FROM cf_tracker_staging
            ON CONFLICT (day) DO UPDATE SET {update_clause}, synced_at = now();
        """))
        conn.execute(text("DROP TABLE cf_tracker_staging;"))
    return len(df)