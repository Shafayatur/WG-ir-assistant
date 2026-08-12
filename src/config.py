"""
Central place for all configuration/secrets. Every other module reads
config from here instead of calling os.environ directly, so there is
exactly one place that knows about env var names.
"""
import os
from dotenv import load_dotenv

load_dotenv()  # reads .env if present; on Streamlit Cloud, secrets are
                # injected as real env vars instead, so this is a no-op there


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Check your .env file (see .env.example)."
        )
    return value


class Config:
    GOOGLE_SERVICE_ACCOUNT_FILE = _require("GOOGLE_SERVICE_ACCOUNT_FILE")
    GOOGLE_SHEET_ORDER_ID = _require("GOOGLE_SHEET_ORDER_ID")
    GOOGLE_SHEET_CF_TRACKER_ID = _require("GOOGLE_SHEET_CF_TRACKER_ID")
    CF_TRACKER_WORKSHEET_NAME = os.environ.get("CF_TRACKER_WORKSHEET_NAME", "CF Update Tracker")
    NEON_DATABASE_URL = _require("NEON_DATABASE_URL")
    # Gemini/passkey are required later (Phase 2/3), not for the sync script,
    # so they're read lazily instead of at import time.
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    APP_PASSKEY = os.environ.get("APP_PASSKEY")
