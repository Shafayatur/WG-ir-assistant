"""
The query layer: every function here runs real SQL against Neon and
returns plain data (dict / DataFrame). Nothing here talks to an LLM.

This is the single source of truth for "what can be asked about the
data." Phase 3 will expose these as (a) fixed dashboard buttons and
(b) tool-call targets for the chatbot - both call the exact same
functions, so behavior never diverges between the two interfaces.

Design rule: any "latest" / "current" notion of CF tracker data must use
get_latest_cf_day(), never MAX(day) directly - the sheet has empty
placeholder rows pre-filled for future dates (confirmed: through
2026-08-31, real data ends 2026-08-03).
"""
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import text

from src.db import get_engine


def _query(sql: str, params: Optional[dict] = None) -> pd.DataFrame:
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


# ---------------------------------------------------------------------------
# CF Tracker queries
# ---------------------------------------------------------------------------

def get_latest_cf_day() -> Optional[date]:
    """The most recent day that actually has data - excludes the sheet's
    empty pre-filled future placeholder rows."""
    df = _query("""
        SELECT MAX(day) AS latest_day FROM cf_tracker
        WHERE registrations IS NOT NULL;
    """)
    return df.iloc[0]["latest_day"]


def get_cf_summary(start_date: Optional[date] = None, end_date: Optional[date] = None) -> dict:
    """Totals across the CF tracker for a date range. Defaults to the
    full range of real data (up to the latest real day, never the empty
    placeholder rows)."""
    if end_date is None:
        end_date = get_latest_cf_day()
    if start_date is None:
        start_date = _query("SELECT MIN(day) AS d FROM cf_tracker;").iloc[0]["d"]

    df = _query("""
        SELECT
            SUM(registrations) AS total_registrations,
            SUM(tickets_booked) AS total_tickets_booked,
            SUM(tickets_invested) AS total_tickets_invested,
            SUM(new_investors) AS total_new_investors,
            SUM(old_investors) AS total_old_investors,
            SUM(investment_value) AS total_investment_value,
            SUM(payables) AS total_payables,
            COUNT(*) AS days_counted
        FROM cf_tracker
        WHERE day BETWEEN :start_date AND :end_date;
    """, {"start_date": start_date, "end_date": end_date})

    result = df.iloc[0].to_dict()
    result["start_date"] = start_date
    result["end_date"] = end_date
    return result


def compare_cf_periods(period: str = "month", n_periods: int = 6) -> pd.DataFrame:
    """Trend of CF tracker metrics grouped by day/week/month, most recent
    n_periods only, ending at the latest real day."""
    if period not in ("day", "week", "month"):
        raise ValueError("period must be 'day', 'week', or 'month'")

    latest_day = get_latest_cf_day()

    df = _query(f"""
        SELECT
            date_trunc(:period, day) AS period_start,
            SUM(registrations) AS registrations,
            SUM(tickets_invested) AS tickets_invested,
            SUM(new_investors) AS new_investors,
            SUM(old_investors) AS old_investors,
            SUM(investment_value) AS investment_value
        FROM cf_tracker
        WHERE day <= :latest_day
        GROUP BY period_start
        ORDER BY period_start DESC
        LIMIT :n_periods;
    """, {"period": period, "latest_day": latest_day, "n_periods": n_periods})

    return df.sort_values("period_start").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Orders queries
# ---------------------------------------------------------------------------

VALID_ORDER_FILTERS = {
    "stage", "status", "project_name", "tenure",
    "min_amount", "max_amount", "start_date", "end_date",
}


def filter_orders(
    stage: Optional[str] = None,
    status: Optional[str] = None,
    project_name: Optional[str] = None,
    tenure: Optional[int] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = 500,
) -> pd.DataFrame:
    """Flexible order filter. All params optional - None means 'no filter
    on this field'. This is the workhorse function most chatbot questions
    will map to."""
    where_clauses = []
    params: dict = {"limit": limit}

    if stage:
        where_clauses.append("stage = :stage")
        params["stage"] = stage
    if status:
        where_clauses.append("status = :status")
        params["status"] = status
    if project_name:
        where_clauses.append("project_name ILIKE :project_name")
        params["project_name"] = f"%{project_name}%"
    if tenure:
        where_clauses.append("tenure = :tenure")
        params["tenure"] = tenure
    if min_amount is not None:
        where_clauses.append("base_grand_total >= :min_amount")
        params["min_amount"] = min_amount
    if max_amount is not None:
        where_clauses.append("base_grand_total <= :max_amount")
        params["max_amount"] = max_amount
    if start_date:
        where_clauses.append("order_created_at >= :start_date")
        params["start_date"] = start_date
    if end_date:
        where_clauses.append("order_created_at <= :end_date")
        params["end_date"] = end_date

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    return _query(f"""
        SELECT id, increment_id, status, stage, project_name, tenure,
               base_grand_total, returned_amount, profit_min, profit_max,
               order_created_at, invested_created_at, close_date,
               customer_unique_id, customer_name, customer_phone, customer_email
        FROM orders
        {where_sql}
        ORDER BY order_created_at DESC
        LIMIT :limit;
    """, params)


def get_order_summary(
    stage: Optional[str] = None,
    project_name: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> dict:
    """Aggregate totals over orders matching the given filters - counts,
    sum invested, sum returned."""
    where_clauses = []
    params: dict = {}

    if stage:
        where_clauses.append("stage = :stage")
        params["stage"] = stage
    if project_name:
        where_clauses.append("project_name ILIKE :project_name")
        params["project_name"] = f"%{project_name}%"
    if start_date:
        where_clauses.append("order_created_at >= :start_date")
        params["start_date"] = start_date
    if end_date:
        where_clauses.append("order_created_at <= :end_date")
        params["end_date"] = end_date

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    df = _query(f"""
        SELECT
            COUNT(*) AS order_count,
            COUNT(DISTINCT customer_unique_id) AS unique_investor_count,
            SUM(base_grand_total) AS total_amount,
            SUM(returned_amount) AS total_returned,
            AVG(base_grand_total) AS avg_order_amount
        FROM orders
        {where_sql};
    """, params)

    return df.iloc[0].to_dict()


def top_investors(n: int = 10, stage: Optional[str] = None) -> pd.DataFrame:
    """Top investors by total invested amount, grouped by
    customer_unique_id, with the most recent known name/contact info for
    that investor attached (one investor can have multiple orders with
    the same unique id but occasionally slightly different name spelling
    across orders - this takes the most recent order's name)."""
    where_sql = "WHERE stage = :stage" if stage else ""
    params = {"n": n}
    if stage:
        params["stage"] = stage

    return _query(f"""
        WITH ranked AS (
            SELECT
                customer_unique_id, customer_name, customer_phone, customer_email,
                base_grand_total, order_created_at,
                ROW_NUMBER() OVER (
                    PARTITION BY customer_unique_id ORDER BY order_created_at DESC
                ) AS rn
            FROM orders
            {where_sql}
        )
        SELECT
            customer_unique_id,
            MAX(customer_name) FILTER (WHERE rn = 1) AS customer_name,
            MAX(customer_phone) FILTER (WHERE rn = 1) AS customer_phone,
            MAX(customer_email) FILTER (WHERE rn = 1) AS customer_email,
            COUNT(*) AS order_count,
            SUM(base_grand_total) AS total_invested
        FROM ranked
        GROUP BY customer_unique_id
        ORDER BY total_invested DESC
        LIMIT :n;
    """, params)


def compare_order_periods(period: str = "month", n_periods: int = 6) -> pd.DataFrame:
    """Trend of order volume/value grouped by day/week/month, based on
    order_created_at."""
    if period not in ("day", "week", "month"):
        raise ValueError("period must be 'day', 'week', or 'month'")

    df = _query("""
        SELECT
            date_trunc(:period, order_created_at) AS period_start,
            COUNT(*) AS order_count,
            SUM(base_grand_total) AS total_amount
        FROM orders
        GROUP BY period_start
        ORDER BY period_start DESC
        LIMIT :n_periods;
    """, {"period": period, "n_periods": n_periods})

    return df.sort_values("period_start").reset_index(drop=True)


def list_projects(limit: int = 50) -> pd.DataFrame:
    """Projects by order volume - useful for the bot to know what valid
    project_name values look like when a user's phrasing is vague."""
    return _query("""
        SELECT project_name, COUNT(*) AS order_count,
               SUM(base_grand_total) AS total_amount
        FROM orders
        GROUP BY project_name
        ORDER BY order_count DESC
        LIMIT :limit;
    """, {"limit": limit})


def search_orders_by_name(name: str, limit: int = 20) -> pd.DataFrame:
    """Finds orders belonging to a customer by (partial, case-insensitive)
    name match. Use this when the user asks about a specific investor by
    name rather than by customer_unique_id."""
    return _query("""
        SELECT id, increment_id, status, stage, project_name,
               base_grand_total, order_created_at, close_date,
               customer_unique_id, customer_name, customer_phone, customer_email
        FROM orders
        WHERE customer_name ILIKE :name
        ORDER BY order_created_at DESC
        LIMIT :limit;
    """, {"name": f"%{name}%", "limit": limit})


# ---------------------------------------------------------------------------
# Investor segments (tier, category, activity status) - precomputed during
# sync from src/segments.py, not recalculated per question.
# ---------------------------------------------------------------------------

def get_investor_segment(name: Optional[str] = None, customer_unique_id: Optional[str] = None) -> pd.DataFrame:
    """Look up one investor's full segment profile (tier, favorite
    category, preferred tenure, activity status, etc.) by name or by
    customer_unique_id. Provide one or the other."""
    if customer_unique_id:
        return _query(
            "SELECT * FROM investor_segments WHERE customer_unique_id = :id;",
            {"id": customer_unique_id},
        )
    return _query(
        "SELECT * FROM investor_segments WHERE customer_name ILIKE :name ORDER BY total_invested DESC;",
        {"name": f"%{name}%"},
    )


def list_investor_segments(
    tier: Optional[str] = None,
    activity_status: Optional[str] = None,
    favorite_category: Optional[str] = None,
    preferred_tenure: Optional[int] = None,
    has_active_investment: Optional[bool] = None,
    min_total_invested: Optional[float] = None,
    limit: int = 30,
) -> pd.DataFrame:
    """Flexible investor segment filter - the main tool for questions like
    'VIP investors with 18-month preferred tenure' or 'inactive High-tier
    investors we should reach out to'. All params optional. Results
    sorted tier first (VIP first), then most-inactive-first within tier -
    a natural outreach priority order."""
    where_clauses = []
    params: dict = {"limit": limit}

    if tier:
        where_clauses.append("tier = :tier")
        params["tier"] = tier
    if activity_status:
        where_clauses.append("activity_status = :activity_status")
        params["activity_status"] = activity_status
    if favorite_category:
        where_clauses.append("favorite_category = :favorite_category")
        params["favorite_category"] = favorite_category
    if preferred_tenure is not None:
        where_clauses.append("preferred_tenure = :preferred_tenure")
        params["preferred_tenure"] = preferred_tenure
    if has_active_investment is not None:
        where_clauses.append("has_active_investment = :has_active")
        params["has_active"] = has_active_investment
    if min_total_invested is not None:
        where_clauses.append("total_invested >= :min_total")
        params["min_total"] = min_total_invested

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    return _query(f"""
        SELECT customer_unique_id, customer_name, tier, total_invested,
               num_investments, favorite_category, preferred_tenure,
               has_active_investment, last_project_name,
               days_since_last_investment, activity_status
        FROM investor_segments
        {where_sql}
        ORDER BY
            CASE tier WHEN 'VIP' THEN 1 WHEN 'High' THEN 2 WHEN 'Mid' THEN 3 ELSE 4 END,
            days_since_last_investment DESC
        LIMIT :limit;
    """, params)


def get_segment_tier_breakdown() -> pd.DataFrame:
    """Count and total invested amount per tier - a quick overview of
    the investor base composition."""
    return _query("""
        SELECT tier, COUNT(*) AS investor_count, SUM(total_invested) AS total_invested,
               AVG(total_invested) AS avg_invested
        FROM investor_segments
        GROUP BY tier
        ORDER BY CASE tier WHEN 'VIP' THEN 1 WHEN 'High' THEN 2 WHEN 'Mid' THEN 3 ELSE 4 END;
    """)