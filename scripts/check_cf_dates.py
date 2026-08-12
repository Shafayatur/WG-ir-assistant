"""
One-off diagnostic: shows which raw 'Day' values in the CF Tracker sheet
did NOT match the expected DD-Mon-YYYY format, so we can see what they
actually look like instead of silently trusting the dateutil fallback.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
from src.sheets_client import fetch_cf_tracker_raw
from src.ingest import _detect_header_row, _slice_with_header, CF_TRACKER_EXPECTED_COLUMNS

raw = fetch_cf_tracker_raw()
known_variants = [v for variants in CF_TRACKER_EXPECTED_COLUMNS.values() for v in variants]
header_row = _detect_header_row(raw, known_variants)
df = _slice_with_header(raw, header_row, CF_TRACKER_EXPECTED_COLUMNS)

day_raw = df["day"].replace("", pd.NA)
strict_parsed = pd.to_datetime(day_raw, format="%d-%b-%Y", errors="coerce")
mismatched = day_raw[strict_parsed.isna() & day_raw.notna()]

print(f"Total day values: {len(day_raw)}")
print(f"Matched DD-Mon-YYYY format: {strict_parsed.notna().sum()}")
print(f"Did NOT match (used fallback parser): {len(mismatched)}")
print("\nSample of mismatched raw values:")
print(mismatched.head(20).tolist())
