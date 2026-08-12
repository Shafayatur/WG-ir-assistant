"""
Finds the most recent CF tracker day that actually has data, vs. the
sheet's pre-filled empty placeholder rows for future dates.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
from sqlalchemy import text
from src.db import get_engine

engine = get_engine()

with engine.connect() as conn:
    print("Most recent day with at least one non-null metric:")
    print(pd.read_sql(text("""
        SELECT MAX(day) FROM cf_tracker
        WHERE investment_value IS NOT NULL
           OR unique_investors IS NOT NULL
           OR registrations IS NOT NULL;
    """), conn))

    print("\nCount of fully-empty future placeholder rows:")
    print(pd.read_sql(text("""
        SELECT COUNT(*) FROM cf_tracker
        WHERE investment_value IS NULL
          AND unique_investors IS NULL
          AND registrations IS NULL
          AND tickets_booked IS NULL
          AND tickets_invested IS NULL;
    """), conn))

    print("\nLast 10 days sorted by day, showing which are real vs empty:")
    print(pd.read_sql(text("""
        SELECT day, registrations, investment_value, unique_investors
        FROM cf_tracker ORDER BY day DESC LIMIT 10;
    """), conn))