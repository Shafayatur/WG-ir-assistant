"""
Investor segmentation logic, ported from wegro-investor-category.ipynb.
This is the single source of truth for these business rules - both the
sync job (which computes and stores the results) and anyone reading the
code should look here, not have the definitions duplicated elsewhere.

Deliberately mirrors the notebook's pandas logic as closely as possible
rather than reimplementing it "cleverly" in SQL - the notebook was
already tested against real data, so matching it exactly minimizes the
risk of the production version quietly behaving differently.

Scope: unlike the original notebook (which filtered to order_created_at
>= 2024-01-01 for that exploration), this uses the FULL order history -
confirmed as the intended production behavior.
"""
import pandas as pd

VALID_STAGES_FOR_SEGMENTATION = ["active", "closed"]  # excludes pending, canceled

PRODUCT_CATEGORIES = {
    "Cattle":        ["cattle", "bull", "calf", "buffalo", "qurbani", "lamb"],
    "Poultry":       ["poultry", "duck", "chicken", "egg trade", "sonali"],
    "Fish":          ["fish", "crab", "tilapia", "hilsha", "pangas", "shrimp", "pabda"],
    "Rice/Paddy":    ["rice", "paddy", "boro", "aman"],
    "Maize/Corn":    ["maize", "corn"],
    "Potato":        ["potato"],
    "Onion":         ["onion"],
    "Spices":        ["chilli", "chili", "turmeric", "mustard"],
    "Jute":          ["jute"],
    "Fruit":         ["mango", "watermelon", "seasonal fruit"],
    "Dairy":         ["dairy", "cheese", "molasses", "honey", "milk"],
    "Goat":          ["goat"],
    "Vegetable":     ["vegetable", "tomato", "cauliflower", "cucumber", "eggplant",
                       "okra", "dherosh", "pumpkin", "garlic", "kochu", "taro"],
    "Commodity Trade": ["commodity"],
    "Agri Input":    ["agricultural input", "fertilizer", "pesticide", "micronutrient",
                       "seed import", "agri machinery", "silage", "seed processing", "seed"],
    "Meat Processing": ["meat processing"],
}


def categorize_product(project_name) -> str:
    name = str(project_name).lower()
    for category, keywords in PRODUCT_CATEGORIES.items():
        for kw in keywords:
            if kw in name:
                return category
    return "Other"


def assign_tier(total_invested: float) -> str:
    if total_invested < 50_000:
        return "Low"
    elif total_invested < 250_000:
        return "Mid"
    elif total_invested < 2_000_000:
        return "High"
    else:
        return "VIP"


def _activity_status(days_since_last) -> str:
    if pd.isna(days_since_last):
        return "Unknown"
    if days_since_last <= 60:
        return "Active"
    elif days_since_last <= 180:
        return "Cooling"
    else:
        return "Inactive - Reach Out"


def _most_common_tenure(tenure_series: pd.Series):
    """How many ORDERS (row count) an investor placed at each tenure
    length - not weighted by amount. Ties broken by picking the longer
    tenure, so results are deterministic regardless of row order."""
    counts = tenure_series.value_counts()
    max_count = counts.max()
    tied_tenures = counts[counts == max_count].index
    return max(tied_tenures)


def compute_investor_segments(orders_df: pd.DataFrame) -> pd.DataFrame:
    """Takes the full cleaned orders DataFrame (as produced by
    ingest.clean_orders) and returns one row per investor with tier,
    category preference, activity status, etc. Full order history is
    used (no date cutoff) - only pending/canceled orders are excluded
    from the underlying calculations, matching the notebook's
    valid_status filter."""
    valid = orders_df[orders_df["stage"].isin(VALID_STAGES_FOR_SEGMENTATION)].copy()
    valid["product_category"] = valid["project_name"].apply(categorize_product)

    investor_summary = valid.groupby("customer_unique_id").agg(
        customer_name=("customer_name", "first"),
        total_invested=("base_grand_total", "sum"),
        num_investments=("id", "count"),
        avg_investment=("base_grand_total", "mean"),
        first_investment=("invested_created_at", "min"),
        last_investment=("invested_created_at", "max"),
    ).reset_index()

    investor_summary["tier"] = investor_summary["total_invested"].apply(assign_tier)

    category_totals = (
        valid.groupby(["customer_unique_id", "product_category"])["base_grand_total"]
        .sum().unstack(fill_value=0)
    )
    favorite_category = category_totals.idxmax(axis=1).rename("favorite_category")

    last_project = (
        valid.sort_values("invested_created_at")
        .groupby("customer_unique_id").last()[["project_name"]]
        .rename(columns={"project_name": "last_project_name"})
    )

    has_active = (
        valid.groupby("customer_unique_id")["stage"]
        .apply(lambda x: (x == "active").any())
        .rename("has_active_investment")
    )

    preferred_tenure = (
        valid.groupby("customer_unique_id")["tenure"]
        .agg(_most_common_tenure)
        .rename("preferred_tenure")
    )

    final = investor_summary.merge(favorite_category, on="customer_unique_id", how="left")
    final = final.merge(last_project, on="customer_unique_id", how="left")
    final = final.merge(has_active, on="customer_unique_id", how="left")
    final = final.merge(preferred_tenure, on="customer_unique_id", how="left")

    today_ref = pd.Timestamp.now().normalize()
    final["days_since_last_investment"] = (today_ref - final["last_investment"]).dt.days
    final["activity_status"] = final["days_since_last_investment"].apply(_activity_status)

    tier_order = ["VIP", "High", "Mid", "Low"]
    final["tier"] = pd.Categorical(final["tier"], categories=tier_order, ordered=True)
    final = final.sort_values(
        ["tier", "days_since_last_investment"], ascending=[True, False]
    ).reset_index(drop=True)
    final["tier"] = final["tier"].astype(str)  # back to plain string for DB storage

    return final