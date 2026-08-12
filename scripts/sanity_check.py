"""
Sanity check: queries Neon directly and prints a few summary numbers, so
we can eyeball that the synced data is sensible before building the query
layer on top of it.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
from sqlalchemy import text
from src.db import get_engine

engine = get_engine()

with engine.connect() as conn:
    print("=" * 60)
    print("ORDERS: count by stage")
    print("=" * 60)
    print(pd.read_sql(text("SELECT stage, status, COUNT(*) FROM orders GROUP BY stage, status ORDER BY stage;"), conn))

    print("\n" + "=" * 60)
    print("ORDERS: total invested amount (active + closed)")
    print("=" * 60)
    print(pd.read_sql(text("""
        SELECT stage, SUM(base_grand_total) AS total_amount, COUNT(*) AS n
        FROM orders
        WHERE stage IN ('active', 'closed')
        GROUP BY stage;
    """), conn))

    print("\n" + "=" * 60)
    print("ORDERS: date range")
    print("=" * 60)
    print(pd.read_sql(text("SELECT MIN(order_created_at), MAX(order_created_at) FROM orders;"), conn))

    print("\n" + "=" * 60)
    print("CF TRACKER: date range and totals")
    print("=" * 60)
    print(pd.read_sql(text("""
        SELECT MIN(day), MAX(day), SUM(investment_value) AS total_investment_value,
               SUM(unique_investors) AS sum_unique_investors
        FROM cf_tracker;
    """), conn))

    print("\n" + "=" * 60)
    print("CF TRACKER: most recent 5 days")
    print("=" * 60)
    print(pd.read_sql(text("SELECT * FROM cf_tracker ORDER BY day DESC LIMIT 5;"), conn))

    print("\n" + "=" * 60)
    print("PII CHECK: confirm sensitive columns were never stored")
    print("=" * 60)
    result = conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'orders'
        AND column_name IN ('customer_name','customer_phone','customer_email',
                             'customer_id','bank_account_name','bank_account_no',
                             'branch_routing_number');
    """))
    leaked = [r[0] for r in result]
    print("Sensitive columns present in orders table:", leaked if leaked else "NONE (correct)")