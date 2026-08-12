"""
One-off diagnostic: lists every tab (worksheet) name in the CF Tracker
Google Sheet, so we can point the sync at the correct one.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google.oauth2.service_account import Credentials
import gspread
from src.config import Config

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

creds = Credentials.from_service_account_file(Config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key(Config.GOOGLE_SHEET_CF_TRACKER_ID)

print("Tabs in this spreadsheet:")
for i, ws in enumerate(spreadsheet.worksheets()):
    print(f"  [{i}] {ws.title}  ({ws.row_count} rows x {ws.col_count} cols)")