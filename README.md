# WeGro IR Assistant

Internal dashboard + AI chatbot for the IR team, built on data synced from
Google Sheets into Neon (Postgres).

## Status: Phase 1 — data layer

Currently implemented: Google Sheets fetch → clean/validate → sync into Neon.
Dashboard UI and chatbot come in later phases.

## Setup

### 1. Virtual environment

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Credentials

- Copy `.env.example` to `.env` and fill in real values.
- Place your Google service account JSON key file in the project root
  (path referenced by `GOOGLE_SERVICE_ACCOUNT_FILE` in `.env`).
- **Never commit `.env` or the service account JSON file** — both are
  already in `.gitignore`.

### 3. Run the sync

```bash
python -m scripts.run_sync
```

This creates the `orders` and `cf_tracker` tables in Neon if they don't
exist yet, then pulls both Google Sheets, cleans them, and upserts the
rows. Safe to re-run — existing rows are updated, not duplicated.

## Project structure

```
src/
  config.py          # loads env vars
  sheets_client.py    # Google Sheets fetch
  ingest.py            # header detection + cleaning for both sheets
  db.py                # Neon schema + upsert logic
scripts/
  run_sync.py          # CLI entry point for the sync
```

## Data notes

- PII columns (customer name/phone/email, bank account name/number,
  routing number) are dropped during ingestion and never stored, even if
  present in the source sheet.
- Order `status` values map to a derived `stage`:
  `pending → invested → disbursement_running → closed`, with `canceled`
  as an exit from `pending`. `is_active` is true for `invested` and
  `disbursement_running`.
