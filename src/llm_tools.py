"""
Thin wrapper around src/queries.py, purely to make return types and
parameter types JSON-safe / LLM-friendly:

- pandas DataFrames -> list of dicts
- date objects -> ISO date strings (both in and out)
- numpy/pandas scalar types -> plain Python int/float

The underlying SQL and business logic all live in queries.py - nothing
here recomputes anything, it only translates types. Each function's
docstring is what Gemini reads to decide when/how to call it, so they
matter as much as the code.
"""
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from src import queries


def _json_safe(obj):
    if isinstance(obj, pd.DataFrame):
        obj = obj.to_dict(orient="records")
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (date, pd.Timestamp)):
        return obj.isoformat()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if np.isnan(obj) else float(obj)
    if isinstance(obj, float) and pd.isna(obj):
        return None
    if obj is pd.NaT:
        return None
    return obj


def _parse_date(s: Optional[str]) -> Optional[date]:
    return date.fromisoformat(s) if s else None


# ---------------------------------------------------------------------------
# Tools exposed to the chatbot - one per queries.py function.
# Keep parameter types to str/int/float/bool so Gemini can build a schema.
# ---------------------------------------------------------------------------

def get_latest_cf_day() -> str:
    """Returns the most recent date (YYYY-MM-DD) for which CF Tracker
    data actually exists. The underlying sheet has empty placeholder rows
    pre-filled for future dates, so always use this instead of assuming
    'today' when the user asks about 'latest' or 'current' data."""
    return _json_safe(queries.get_latest_cf_day())


def get_cf_summary(start_date: Optional[str] = None, end_date: Optional[str] = None) -> dict:
    """Totals from the CF Tracker (registrations, tickets booked/invested,
    new/old investors, investment value, payables) over a date range.
    Dates are YYYY-MM-DD strings. If omitted, covers the full history of
    real data. Use this for questions like 'total investment this month'
    or 'how many new investors last quarter'."""
    result = queries.get_cf_summary(_parse_date(start_date), _parse_date(end_date))
    return _json_safe(result)


def compare_cf_periods(period: str = "month", n_periods: int = 6) -> list:
    """Trend of CF Tracker metrics over time, grouped by 'day', 'week', or
    'month'. Returns the most recent n_periods, oldest first. Use this for
    questions like 'show me the monthly trend' or 'how has investment
    value changed over the last few months'."""
    df = queries.compare_cf_periods(period=period, n_periods=n_periods)
    return _json_safe(df)


def filter_orders(
    stage: Optional[str] = None,
    status: Optional[str] = None,
    project_name: Optional[str] = None,
    tenure: Optional[int] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
) -> list:
    """Returns individual orders matching filters, including investor
    name/phone/email. Prefer get_order_summary instead of this function
    whenever the user wants a total, count, or average rather than a list
    of individual orders - this function returns full row data and is
    more expensive to use in conversation. stage is one of 'pending',
    'active', 'closed', 'canceled' (active = currently invested or
    disbursing; use this unless the user specifically asks about a raw
    status). status is the exact underlying value: 'pending', 'invested',
    'disbursement_running', 'closed', 'canceled'. project_name matches
    partially/case-insensitively. Dates are YYYY-MM-DD strings and filter
    on order_created_at. Bank account numbers and routing numbers are
    never stored/returned - only bank name/branch for context. Keep limit
    small (default 20) unless the user explicitly asks to see many
    individual records. Results are most recent first."""
    df = queries.filter_orders(
        stage=stage, status=status, project_name=project_name, tenure=tenure,
        min_amount=min_amount, max_amount=max_amount,
        start_date=_parse_date(start_date), end_date=_parse_date(end_date),
        limit=limit,
    )
    return _json_safe(df)


def get_order_summary(
    stage: Optional[str] = None,
    project_name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    """Aggregate totals (order count, unique investor count, total
    amount, total returned, average order amount) for orders matching the
    given filters. Use this for questions asking for a total or count
    rather than a list of individual orders. Note: for closed orders,
    total_returned can exceed total_amount because returns include profit
    paid out on top of the principal, not just the principal back."""
    result = queries.get_order_summary(
        stage=stage, project_name=project_name,
        start_date=_parse_date(start_date), end_date=_parse_date(end_date),
    )
    return _json_safe(result)


def top_investors(n: int = 10, stage: Optional[str] = None) -> list:
    """Top investors ranked by total amount invested, including their
    name, phone, and email (bank account numbers are never stored or
    returned). Optionally filter to a specific stage ('active', 'closed',
    etc)."""
    df = queries.top_investors(n=n, stage=stage)
    return _json_safe(df)


def compare_order_periods(period: str = "month", n_periods: int = 6) -> list:
    """Trend of order volume and total amount over time, grouped by
    'day', 'week', or 'month', based on when orders were created. Returns
    the most recent n_periods, oldest first."""
    df = queries.compare_order_periods(period=period, n_periods=n_periods)
    return _json_safe(df)


def list_projects(limit: int = 50) -> list:
    """Lists investment projects with their order count and total amount,
    sorted by order count descending. Use this to look up the exact
    project_name to pass to filter_orders/get_order_summary when the
    user's phrasing doesn't exactly match a project name (e.g. user says
    'rice' - check this list for exact matches like 'Boro Rice Input - 7'
    before filtering)."""
    df = queries.list_projects(limit=limit)
    return _json_safe(df)


def search_orders_by_name(name: str, limit: int = 20) -> list:
    """Finds orders belonging to an investor by (partial, case-insensitive)
    name match - e.g. name='Tanjir' matches 'Md. Tanjir Hossain'. Use this
    whenever the user asks about a specific investor by name. Returns
    that investor's orders with name/phone/email included. If nothing
    matches, returns an empty list - say plainly that no investor by that
    name was found rather than guessing."""
    df = queries.search_orders_by_name(name=name, limit=limit)
    return _json_safe(df)


def get_investor_segment(name: Optional[str] = None, customer_unique_id: Optional[str] = None) -> list:
    """Look up an investor's full segment profile by name or
    customer_unique_id: tier, favorite product category, preferred
    tenure, activity status, total invested, etc. Provide either name or
    customer_unique_id, not both. Use this for questions like 'what tier
    is X in' or 'what does investor X prefer to invest in'."""
    df = queries.get_investor_segment(name=name, customer_unique_id=customer_unique_id)
    return _json_safe(df)


def list_investor_segments(
    tier: Optional[str] = None,
    activity_status: Optional[str] = None,
    favorite_category: Optional[str] = None,
    preferred_tenure: Optional[int] = None,
    has_active_investment: Optional[bool] = None,
    min_total_invested: Optional[float] = None,
    limit: int = 30,
) -> list:
    """The main tool for investor segmentation questions - e.g. 'VIP
    investors with an 18-month preferred tenure', 'inactive High-tier
    investors to reach out to', 'investors whose favorite category is
    Fish'. All parameters optional and combinable.

    tier: one of 'Low' (< 50,000 total invested), 'Mid' (50,000-249,999),
    'High' (250,000-1,999,999), or 'VIP' (>= 2,000,000). Based on total
    amount invested across that investor's full history of orders with
    status invested/disbursement_running/closed (pending and canceled
    orders don't count toward tier).

    activity_status: one of 'Active' (invested within the last 60 days),
    'Cooling' (61-180 days since last investment), or 'Inactive - Reach
    Out' (180+ days since last investment) - all relative to today's
    actual date, not the data sync date.

    favorite_category: the product category (e.g. 'Fish', 'Cattle',
    'Rice/Paddy', 'Poultry', 'Vegetable', etc) this investor has put the
    most total money into, out of all their orders.

    preferred_tenure: the tenure (in months) this investor has chosen
    most often, counted by NUMBER OF ORDERS at that tenure - not by
    money amount. If they've placed an equal number of orders at two
    different tenures, the longer tenure is used as the tiebreaker.

    has_active_investment: true if they currently have at least one
    order in 'invested' or 'disbursement_running' status right now.

    Results are sorted VIP-first, then most-inactive-first within each
    tier - a natural outreach priority order."""
    df = queries.list_investor_segments(
        tier=tier, activity_status=activity_status, favorite_category=favorite_category,
        preferred_tenure=preferred_tenure, has_active_investment=has_active_investment,
        min_total_invested=min_total_invested, limit=limit,
    )
    return _json_safe(df)


def get_segment_tier_breakdown() -> list:
    """Count of investors and total/average amount invested per tier
    (Low/Mid/High/VIP) - a quick overview of the investor base
    composition. Use this for questions like 'how many VIP investors do
    we have' or 'give me a breakdown of investors by tier'."""
    df = queries.get_segment_tier_breakdown()
    return _json_safe(df)


# All tool functions, for the chatbot module to register with Gemini.
ALL_TOOLS = [
    get_latest_cf_day,
    get_cf_summary,
    compare_cf_periods,
    filter_orders,
    get_order_summary,
    top_investors,
    compare_order_periods,
    list_projects,
    search_orders_by_name,
    get_investor_segment,
    list_investor_segments,
    get_segment_tier_breakdown,
]