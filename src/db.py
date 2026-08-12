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


def create_tables():
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(CREATE_ORDERS_TABLE))
        conn.execute(text(CREATE_CF_TRACKER_TABLE))


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
