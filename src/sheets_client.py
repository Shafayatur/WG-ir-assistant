"""
Thin wrapper around gspread for pulling a Google Sheet's first worksheet
into a pandas DataFrame with NO header assumption - every row becomes a
data row. Header-row detection happens later in ingest.py, same pattern
as the original dashboard (sheets sometimes have label rows above the
real headers).
"""
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

from src.config import Config

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _get_client() -> gspread.Client:
    creds = Credentials.from_service_account_file(
        Config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return gspread.authorize(creds)


def fetch_sheet_as_raw_df(sheet_id: str, worksheet_index: int = 0) -> pd.DataFrame:
    """
    Fetch a worksheet by index (default: first tab) and return it as a
    headerless DataFrame (all rows, no column names assigned yet).
    """
    client = _get_client()
    spreadsheet = client.open_by_key(sheet_id)
    worksheet = spreadsheet.get_worksheet(worksheet_index)
    values = worksheet.get_all_values()  # list of lists of strings

    if not values:
        return pd.DataFrame()

    return pd.DataFrame(values)


def fetch_order_sheet_raw() -> pd.DataFrame:
    return fetch_sheet_as_raw_df(Config.GOOGLE_SHEET_ORDER_ID)


def fetch_cf_tracker_raw() -> pd.DataFrame:
    return fetch_sheet_as_raw_df(Config.GOOGLE_SHEET_CF_TRACKER_ID)
