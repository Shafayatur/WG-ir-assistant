"""
Cleans raw (headerless) DataFrames pulled from Google Sheets into the
canonical schemas we store in Neon.

Header-row detection is generalized from the original dashboard's logic:
sheets can have a stray label row above the real headers, so we scan the
first few rows and pick the one that best matches known column names,
instead of assuming row 0 is always the header.

Columns that could identify a person (name, phone, email, bank account
number/name, routing number) are dropped here explicitly, even if the
source sheet still contains them. This is intentional defense-in-depth:
even if someone forgets to strip them from the sheet upstream, they never
reach the database or the LLM.
"""
import pandas as pd

# ---------------------------------------------------------------------------
# Column name variants -> canonical name, per sheet.
# ---------------------------------------------------------------------------

ORDER_EXPECTED_COLUMNS = {
    "id": ["id"],
    "increment_id": ["increment_id"],
    "is_insurance_applied": ["is_insurance_applied"],
    "base_sub_total": ["base_sub_total"],
    "base_grand_total": ["base_grand_total"],
    "returned_amount": ["returned_amount"],
    "status": ["status"],
    "customer_unique_id": ["customer_unique_id"],
    "customer_created_at": ["customer_created_at"],
    "project_name": ["project_name"],
    "tenure": ["tenure"],
    "remark": ["remark"],
    "order_created_at": ["order_created_at"],
    "invested_created_at": ["invested_created_at"],
    "transaction_count": ["transaction_count"],
    "return_count": ["return_count"],
    "returned_created_at": ["returned_created_at"],
    "close_date": ["close_date"],
    "profit_min": ["profit_min"],
    "profit_max": ["profit_max"],
    "opa_id": ["opa_id"],
    "bank_attachment_date": ["bank_attachment_date"],
    "bank_name": ["bank_name"],
    "bank_branch": ["bank_branch"],
}

# Explicitly never keep these, even if present in the source sheet.
ORDER_PII_COLUMNS = [
    "customer_name", "customer_phone", "customer_email", "customer_id",
    "bank_account_name", "bank_account_no", "branch_routing_number",
]

CF_TRACKER_EXPECTED_COLUMNS = {
    "day": ["day"],
    "registrations": ["number of registration (interest)", "number of registration", "registration"],
    "tickets_booked": ["number of tickets booked (consideration)", "tickets booked"],
    "tickets_invested": ["number of tickets invested", "tickets invested"],
    "unique_investors": ["number of unique investors", "unique investors"],
    "new_investors": ["number of new unique investors", "new unique investors"],
    "old_investors": ["number of old unique investors", "old unique investors"],
    "investment_value": ["investment in value (payment)", "investment in value", "investment value"],
    "payables": ["payables"],
}

# status -> lifecycle stage, confirmed with the IR team:
# pending -> invested -> disbursement_running -> closed, canceled exits from pending
STATUS_TO_STAGE = {
    "pending": "pending",
    "canceled": "canceled",
    "invested": "active",
    "disbursement_running": "active",
    "closed": "closed",
}
ACTIVE_STATUSES = {"invested", "disbursement_running"}


def _normalize_header(col) -> str:
    return str(col).strip().lower()


def _detect_header_row(raw_df: pd.DataFrame, known_variants: list, max_scan: int = 10) -> int:
    best_row, best_score = 0, -1
    for i in range(min(max_scan, len(raw_df))):
        row_values = [_normalize_header(v) for v in raw_df.iloc[i].tolist()]
        score = sum(1 for val in row_values if val in known_variants)
        if score > best_score:
            best_row, best_score = i, score
    return best_row


def _map_columns(header_row_values: list, expected_columns: dict) -> dict:
    normalized = {_normalize_header(c): idx for idx, c in enumerate(header_row_values)}
    mapping = {}
    for canonical, variants in expected_columns.items():
        for variant in variants:
            if variant in normalized:
                mapping[canonical] = normalized[variant]
                break
    return mapping


def _slice_with_header(raw_df: pd.DataFrame, header_row: int, expected_columns: dict) -> pd.DataFrame:
    header_values = raw_df.iloc[header_row].tolist()
    col_map = _map_columns(header_values, expected_columns)

    missing = [c for c in expected_columns if c not in col_map]
    if missing:
        raise ValueError(
            f"Could not find expected columns in sheet: {missing}. "
            f"Header row found was: {header_values}"
        )

    data = raw_df.iloc[header_row + 1:].copy().reset_index(drop=True)
    result = pd.DataFrame({
        canonical: data.iloc[:, idx] for canonical, idx in col_map.items()
    })
    return result


def _parse_date_column(series: pd.Series) -> pd.Series:
    """Sheets use 'DD-Mon-YYYY' (e.g. 03-Aug-2026). Falls back to a looser
    parse for any rows that don't match, rather than dropping them silently."""
    series = series.replace("", pd.NA)
    parsed = pd.to_datetime(series, format="%d-%b-%Y", errors="coerce")
    still_missing = parsed.isna() & series.notna()
    if still_missing.any():
        parsed.loc[still_missing] = pd.to_datetime(
            series[still_missing], errors="coerce", dayfirst=True
        )
    return parsed


def _to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.replace("", pd.NA), errors="coerce")


# ---------------------------------------------------------------------------
# Public: clean_orders / clean_cf_tracker
# ---------------------------------------------------------------------------

def clean_orders(raw_df: pd.DataFrame) -> pd.DataFrame:
    known_variants = [v for variants in ORDER_EXPECTED_COLUMNS.values() for v in variants]
    header_row = _detect_header_row(raw_df, known_variants)
    df = _slice_with_header(raw_df, header_row, ORDER_EXPECTED_COLUMNS)

    date_cols = [
        "customer_created_at", "order_created_at", "invested_created_at",
        "returned_created_at", "close_date", "bank_attachment_date",
    ]
    for col in date_cols:
        df[col] = _parse_date_column(df[col])

    numeric_cols = [
        "id", "base_sub_total", "base_grand_total",
        "returned_amount", "tenure", "transaction_count", "return_count",
        "profit_min", "profit_max", "opa_id",
    ]
    for col in numeric_cols:
        df[col] = _to_numeric(df[col])

    # Sheets stores this as 0/1, but the Neon column is BOOLEAN - cast
    # explicitly so pandas writes real bool values, not int64.
    df["is_insurance_applied"] = _to_numeric(df["is_insurance_applied"]).fillna(0).astype(int).astype(bool)

    df["status"] = df["status"].str.strip().str.lower()
    df["stage"] = df["status"].map(STATUS_TO_STAGE)
    df["is_active"] = df["status"].isin(ACTIVE_STATUSES)

    for col in ["increment_id", "customer_unique_id", "project_name",
                "remark", "bank_name", "bank_branch"]:
        df[col] = df[col].replace("", pd.NA)

    df = df.dropna(subset=["id"])
    df["id"] = df["id"].astype(int)
    df = df.drop_duplicates(subset=["id"], keep="last")

    return df


def clean_cf_tracker(raw_df: pd.DataFrame) -> pd.DataFrame:
    known_variants = [v for variants in CF_TRACKER_EXPECTED_COLUMNS.values() for v in variants]
    header_row = _detect_header_row(raw_df, known_variants)
    df = _slice_with_header(raw_df, header_row, CF_TRACKER_EXPECTED_COLUMNS)

    df["day"] = _parse_date_column(df["day"])
    df = df.dropna(subset=["day"])

    numeric_cols = [
        "registrations", "tickets_booked", "tickets_invested",
        "unique_investors", "new_investors", "old_investors",
        "investment_value", "payables",
    ]
    for col in numeric_cols:
        df[col] = _to_numeric(df[col])

    df = df.drop_duplicates(subset=["day"], keep="last")
    df = df.sort_values("day").reset_index(drop=True)

    return df
