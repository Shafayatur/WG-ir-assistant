"""
Manual sync trigger: pulls both Google Sheets, cleans them, and upserts
into Neon. Run this from the project root:

    python -m scripts.run_sync

This will become the "Refresh from Google Sheets" button's backend call
in the Streamlit app (Phase 3) - same function, just triggered from a
button instead of the CLI.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.sheets_client import fetch_order_sheet_raw, fetch_cf_tracker_raw
from src.ingest import clean_orders, clean_cf_tracker
from src.db import create_tables, upsert_orders, upsert_cf_tracker


def main():
    print("Creating tables if they don't exist...")
    create_tables()

    print("Fetching Order sheet from Google Sheets...")
    raw_orders = fetch_order_sheet_raw()
    print(f"  -> {len(raw_orders)} raw rows fetched")

    print("Cleaning Order data...")
    orders_df = clean_orders(raw_orders)
    print(f"  -> {len(orders_df)} clean rows")

    print("Upserting Orders into Neon...")
    n = upsert_orders(orders_df)
    print(f"  -> {n} rows upserted")

    print("Fetching CF Tracker sheet from Google Sheets...")
    raw_cf = fetch_cf_tracker_raw()
    print(f"  -> {len(raw_cf)} raw rows fetched")

    print("Cleaning CF Tracker data...")
    cf_df = clean_cf_tracker(raw_cf)
    print(f"  -> {len(cf_df)} clean rows")

    print("Upserting CF Tracker into Neon...")
    n = upsert_cf_tracker(cf_df)
    print(f"  -> {n} rows upserted")

    print("Sync complete.")


if __name__ == "__main__":
    main()
