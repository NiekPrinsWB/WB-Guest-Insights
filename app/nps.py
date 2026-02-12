"""
Westerbergen Guest Insights - NPS Calculation Engine
"""
import pandas as pd
from app.config import NPS_PROMOTER_MIN, NPS_PASSIVE_MIN


def calc_nps(df, min_responses=1):
    """
    Calculate NPS from a DataFrame that has a 'score' column.
    Returns dict with nps, promoters%, passives%, detractors%, n.
    Returns None if insufficient data.
    """
    scores = df["score"].dropna()
    n = len(scores)
    if n < min_responses:
        return None

    promoters = (scores >= NPS_PROMOTER_MIN).sum()
    detractors = (scores < NPS_PASSIVE_MIN).sum()

    pct_promoters = promoters / n * 100
    pct_detractors = detractors / n * 100
    nps = pct_promoters - pct_detractors

    return {
        "nps": round(nps, 1),
        "pct_promoters": round(pct_promoters, 1),
        "pct_passives": round(100 - pct_promoters - pct_detractors, 1),
        "pct_detractors": round(pct_detractors, 1),
        "n": n,
        "avg_score": round(scores.mean(), 2),
    }


def nps_by_group(df, group_col, min_responses=5):
    """Calculate NPS grouped by a column."""
    results = []
    for name, group in df.groupby(group_col):
        result = calc_nps(group, min_responses)
        if result:
            result[group_col] = name
            results.append(result)
    return pd.DataFrame(results)


def nps_trend(df, period="week"):
    """
    Calculate NPS trend over time.
    period: 'week' or 'maand'
    """
    if period == "week":
        group_cols = ["jaar", "week"]
    else:
        group_cols = ["jaar", "maand"]

    results = []
    for keys, group in df.groupby(group_cols):
        result = calc_nps(group, min_responses=1)
        if result:
            if period == "week":
                result["jaar"] = keys[0]
                result["week"] = keys[1]
                # Create approximate date for x-axis
                try:
                    result["datum"] = pd.Timestamp.fromisocalendar(
                        int(keys[0]), int(keys[1]), 1
                    )
                except (ValueError, TypeError):
                    continue
            else:
                result["jaar"] = keys[0]
                result["maand"] = keys[1]
                try:
                    result["datum"] = pd.Timestamp(year=int(keys[0]), month=int(keys[1]), day=1)
                except (ValueError, TypeError):
                    continue
            results.append(result)

    trend_df = pd.DataFrame(results)
    if not trend_df.empty:
        trend_df = trend_df.sort_values("datum")
    return trend_df


def nps_yoy(df):
    """Year-over-year NPS comparison by category."""
    results = []
    for (jaar, cat), group in df.groupby(["jaar", "categorie"]):
        result = calc_nps(group, min_responses=5)
        if result:
            result["jaar"] = jaar
            result["categorie"] = cat
            results.append(result)
    return pd.DataFrame(results)


def leaderboard(df, col="objectnaam", min_responses=5, top_n=10, ascending=True):
    """
    Generate leaderboard of best or worst scoring items.
    ascending=True -> worst first (bottom), ascending=False -> best first (top)
    """
    nps_df = nps_by_group(df, col, min_responses)
    if nps_df.empty:
        return nps_df

    nps_df = nps_df.sort_values("nps", ascending=ascending).head(top_n)
    return nps_df
