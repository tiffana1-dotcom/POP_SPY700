"""
TrendScout Live — Streamlit buyer dashboard.
Loads product rows from temp_amazon.json (same folder as this file).
Run: streamlit run TrendScout.py
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

import env_setup

env_setup.load_pop_dotenv()

from trendscout_sidebar import SORT_LABELS, render_explore_sidebar

# ---------------------------------------------------------------------------
# Commercial risk tier (heuristic — for filtering & badges, not legal advice)
# ---------------------------------------------------------------------------

RISK_LEVEL_OPTIONS: tuple[str, ...] = ("Low Risk", "Needs Review", "High Risk")


def estimate_risk_level(row: pd.Series) -> str:
    """Heuristic sourcing risk: listing quality + claim red-flag keywords."""
    r = row.get("rating")
    rating = float(r) if pd.notna(r) else 0.0
    rev = int(row.get("review_count") or 0)
    ben = str(row.get("product_benefits") or "").lower()
    bull = row.get("bullets")
    blob = ben
    if isinstance(bull, list):
        blob = (ben + " " + " ".join(str(x) for x in bull)).lower()
    red = (
        "fda approved",
        "fda cleared",
        "cure ",
        "cures",
        "treats disease",
        "diagnose",
        "miracle",
        "guaranteed results",
        "clinically proven",
        "lose weight fast",
    )
    if any(k in blob for k in red) or rating < 3.5 or (rating < 4.0 and rev < 25):
        return "High Risk"
    if rating < 4.35 or rev < 80 or (not str(row.get("product_shelf_life") or "").strip() and len(ben) < 8):
        return "Needs Review"
    return "Low Risk"


def risk_badge_class(tier: str) -> str:
    return {
        "Low Risk": "badge-risk badge-risk-low",
        "Needs Review": "badge-risk badge-risk-mid",
        "High Risk": "badge-risk badge-risk-high",
    }.get(tier, "badge-risk badge-risk-mid")


# ---------------------------------------------------------------------------
# Paths & data loading
# ---------------------------------------------------------------------------

DATA_FILE = Path(__file__).resolve().parent / "temp_amazon.json"

# Product benefits themes → keyword hints (matched on `product_benefits` text, case-insensitive).
# If multiple categories are selected, a row matches if it satisfies any selected theme (OR).
BENEFIT_CATEGORIES: dict[str, dict[str, object]] = {
    "low_calorie": {
        "label": "Low Calorie",
        "patterns": (
            "low calorie",
            "low-calorie",
            "zero calorie",
            "0 calorie",
            "calorie free",
            "sugar free",
            "no sugar",
            "less sugar",
            "reduced calorie",
        ),
    },
    "antioxidant_rich": {
        "label": "Antioxidant Rich",
        "patterns": (
            "antioxidant",
            "antioxidants",
            "polyphenol",
            "catechin",
            "egcg",
            "flavonoid",
        ),
    },
    "healthy_refreshment": {
        "label": "Healthy Refreshment",
        "patterns": (
            "refreshment",
            "refreshing",
            "hydration",
            "hydrating",
            "healthy refreshment",
            "replenish",
            "thirst",
        ),
    },
}


def row_matches_benefit_categories(row: pd.Series, selected_ids: list[str]) -> bool:
    """True if no filter, or Product benefits text matches any selected theme."""
    if not selected_ids:
        return True
    blob = str(row.get("product_benefits") or "").lower()
    if not blob.strip():
        return False
    for sid in selected_ids:
        meta = BENEFIT_CATEGORIES.get(sid)
        if not meta:
            continue
        patterns: tuple[str, ...] = meta["patterns"]  # type: ignore[assignment]
        if any(p in blob for p in patterns):
            return True
    return False


def _clean_text_field(val: object) -> str:
    """Normalize JSON null / empty to empty string for shelf life & benefits."""
    if val is None:
        return ""
    if isinstance(val, float) and pd.isna(val):
        return ""
    s = str(val).strip()
    return s


def parse_price_to_float(price: object) -> float:
    if price is None or (isinstance(price, float) and np.isnan(price)):
        return float("nan")
    s = str(price).strip()
    if not s:
        return float("nan")
    s = re.sub(r"[^\d.]", "", s)
    if not s:
        return float("nan")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def load_products(path: Path | None = None) -> pd.DataFrame:
    p = path or DATA_FILE
    if not p.exists():
        st.error(f"Data file not found: {p}")
        return pd.DataFrame()

    with open(p, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        st.error("Expected JSON array of products.")
        return pd.DataFrame()

    df = pd.DataFrame(raw)

    if "amazon_title" not in df.columns and "search_result_title" in df.columns:
        df["amazon_title"] = df["search_result_title"]

    df["price_num"] = df["price"].apply(parse_price_to_float)
    df["rating"] = pd.to_numeric(df.get("rating"), errors="coerce")
    df["review_count"] = pd.to_numeric(df.get("review_count"), errors="coerce").fillna(0).astype(int)
    df["search_result_rank_used"] = pd.to_numeric(
        df.get("search_result_rank_used"), errors="coerce"
    ).fillna(99)

    if "status" in df.columns:
        df_ok = df[df["status"].astype(str).str.lower() == "ok"].copy()
        if len(df_ok) > 0:
            df = df_ok

    df["bullets"] = df["bullets"].apply(
        lambda x: x if isinstance(x, list) else ([] if pd.isna(x) else [str(x)])
    )
    df["query"] = df.get("query", "").fillna("").astype(str)
    df["asin"] = df.get("asin", "").fillna("").astype(str)
    df["url"] = df.get("url", "").fillna("").astype(str)
    df["amazon_title"] = df.get("amazon_title", "").fillna("").astype(str)

    # Listing-derived fields (from scrape / JSON)
    if "Product Shelf Life" in df.columns:
        df["product_shelf_life"] = df["Product Shelf Life"].map(_clean_text_field)
    else:
        df["product_shelf_life"] = ""

    if "Product Benefits" in df.columns:
        df["product_benefits"] = df["Product Benefits"].map(_clean_text_field)
    else:
        df["product_benefits"] = ""

    df["opportunity_score"] = df.apply(compute_opportunity_score, axis=1)
    df["risk_level"] = df.apply(estimate_risk_level, axis=1)
    return df


# ---------------------------------------------------------------------------
# Scoring & reasons
# ---------------------------------------------------------------------------


def compute_opportunity_score(row: pd.Series) -> float:
    """Simple 0–100 score: rating, reviews, price, search rank."""
    r = row.get("rating")
    if pd.isna(r) or r is None:
        r = 0.0
    else:
        r = float(r)
    reviews = float(row.get("review_count") or 0)
    price = row.get("price_num")
    rank = float(row.get("search_result_rank_used") or 50)

    rating_pts = (r / 5.0) * 28.0
    review_pts = min(28.0, np.log1p(max(0, reviews)) / np.log1p(50000) * 28.0)

    if pd.isna(price) or price <= 0:
        price_pts = 10.0
    else:
        price_pts = min(22.0, 22.0 * (25.0 / (25.0 + float(price))))

    rank_pts = max(0.0, 22.0 * (1.0 - min(rank - 1.0, 24.0) / 24.0))

    return float(np.clip(rating_pts + review_pts + price_pts + rank_pts, 0.0, 100.0))


def short_reasons(row: pd.Series) -> list[str]:
    reasons: list[str] = []
    r = row.get("rating")
    if pd.notna(r) and float(r) >= 4.5:
        reasons.append("High rating")
    rev = int(row.get("review_count") or 0)
    if rev >= 500:
        reasons.append("Strong review count")
    elif rev >= 100:
        reasons.append("Solid review volume")

    p = row.get("price_num")
    if pd.notna(p) and p <= 15:
        reasons.append("Good entry price")
    elif pd.notna(p) and p <= 35:
        reasons.append("Reasonable price point")

    rank = row.get("search_result_rank_used")
    if pd.notna(rank) and float(rank) <= 3:
        reasons.append("Strong search placement")

    if not reasons:
        reasons.append("Balanced signals vs. peers")
    return reasons[:4]


def top_recommendations(df_sorted: pd.DataFrame) -> pd.DataFrame:
    """Top 5 SKUs after the active sort (one row per ASIN, stable order)."""
    if df_sorted.empty:
        return df_sorted
    return df_sorted.drop_duplicates(subset=["asin"], keep="first").head(5)


def apply_filters(
    df: pd.DataFrame,
    q: str,
    queries: list[str],
    benefit_category_ids: list[str],
    min_rating: float,
    price_min: float,
    price_max: float,
) -> pd.DataFrame:
    out = df.copy()
    if q.strip():
        ql = q.lower()
        mask = (
            out["amazon_title"].str.lower().str.contains(ql, na=False)
            | out["query"].str.lower().str.contains(ql, na=False)
            | out["asin"].str.lower().str.contains(ql, na=False)
        )
        out = out[mask]
    if queries:
        out = out[out["query"].isin(queries)]
    if benefit_category_ids:
        out = out[out.apply(lambda r: row_matches_benefit_categories(r, benefit_category_ids), axis=1)]
    out = out[out["rating"].fillna(0) >= min_rating]
    pn = out["price_num"]
    out = out[pn.isna() | ((pn >= price_min) & (pn <= price_max))]
    return out


def sort_dataframe(df: pd.DataFrame, sort_key: str) -> pd.DataFrame:
    """Sort filtered rows; secondary keys break ties so order is not arbitrary."""
    out = df.copy()
    if sort_key == "highest_rating":
        return out.sort_values(
            ["rating", "review_count", "opportunity_score", "asin"],
            ascending=[False, False, False, True],
            na_position="last",
        )
    if sort_key == "most_reviews":
        return out.sort_values(
            ["review_count", "rating", "opportunity_score", "asin"],
            ascending=[False, False, False, True],
        )
    if sort_key == "lowest_price":
        return out.sort_values(
            ["price_num", "rating", "review_count", "asin"],
            ascending=[True, False, False, True],
            na_position="last",
        )
    if sort_key == "best_opportunity":
        return out.sort_values(
            ["opportunity_score", "review_count", "rating", "asin"],
            ascending=[False, False, False, True],
        )
    return out


def filter_fingerprint(
    search: str,
    q_pick: list[str],
    benefit_pick: list[str],
    min_rating: float,
    pr_min: float,
    pr_max: float,
    n_filtered: int,
) -> str:
    return "|".join(
        [
            search.strip(),
            ",".join(sorted(q_pick)),
            ",".join(sorted(benefit_pick)),
            f"{min_rating:.2f}",
            f"{pr_min:.2f}",
            f"{pr_max:.2f}",
            str(n_filtered),
        ]
    )


def price_display(row: pd.Series) -> str:
    if isinstance(row.get("price"), str) and row.get("price"):
        return str(row["price"])
    if pd.notna(row.get("price_num")):
        return f"${float(row['price_num']):.2f}"
    return "—"


# ---------------------------------------------------------------------------
# UI — CSS (premium B2B sourcing — minimal, neutral)
# ---------------------------------------------------------------------------

CUSTOM_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
  :root {
    --bg: #fafafa;
    --surface: #ffffff;
    --line: #e8e8e8;
    --line-strong: #d4d4d4;
    --text: #171717;
    --text-2: #525252;
    --text-3: #737373;
    --accent: #262626;
    --accent-soft: #f5f5f5;
    --font: 'Inter', ui-sans-serif, system-ui, -apple-system, sans-serif;
  }
  .stApp {
    background: var(--bg) !important;
    font-family: var(--font) !important;
  }
  header[data-testid="stHeader"],
  [data-testid="stHeader"] {
    display: flex !important;
    align-items: center !important;
    visibility: visible !important;
    height: auto !important;
    min-height: 2.75rem !important;
    max-height: none !important;
    overflow: visible !important;
    padding: 0.35rem 0.75rem !important;
    margin: 0 !important;
    border: none !important;
    border-bottom: 1px solid var(--line) !important;
    background: var(--surface) !important;
    box-shadow: none !important;
    position: relative !important;
    z-index: 1002 !important;
  }
  [data-testid="stExpandSidebarButton"],
  header[data-testid="stHeader"] button {
    visibility: visible !important;
    opacity: 1 !important;
    pointer-events: auto !important;
    z-index: 10050 !important;
    position: relative !important;
  }
  header[data-testid="stHeader"] {
    pointer-events: auto !important;
    z-index: 10040 !important;
  }
  [data-testid="stSidebar"],
  section[data-testid="stSidebar"] {
    visibility: visible !important;
    opacity: 1 !important;
  }
  /* Do NOT hide [data-testid="stToolbar"] — it contains stExpandSidebarButton; hiding it removes the sidebar toggle. */
  [data-testid="stDecoration"] {
    display: none !important;
  }
  [data-testid="stAppViewContainer"] {
    padding-top: 0 !important;
    margin-top: 0 !important;
  }
  [data-testid="stAppViewContainer"] > section[data-testid="stMain"],
  section.main,
  .main {
    padding-top: 0 !important;
    margin-top: 0 !important;
  }
  .block-container {
    padding-top: 1.75rem !important;
    padding-bottom: 5rem !important;
    max-width: 1200px !important;
  }
  [data-testid="stSidebar"] {
    background: #f7f7f7 !important;
    border-right: 1px solid var(--line) !important;
  }
  [data-testid="stSidebar"] .block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 2rem !important;
    padding-left: 1.25rem !important;
    padding-right: 1.25rem !important;
  }
  [data-testid="stSidebar"] h3 {
    font-size: 0.65rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    color: var(--text-3) !important;
    margin-bottom: 0.65rem !important;
  }
  [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] .stMarkdown p {
    color: var(--text-2) !important;
    font-size: 0.8125rem !important;
  }
  [data-testid="stSidebar"] [data-baseweb="select"] > div,
  [data-testid="stSidebar"] input {
    border-radius: 6px !important;
    border-color: var(--line) !important;
    background: var(--surface) !important;
    font-size: 0.8125rem !important;
  }
  [data-testid="stSidebar"] .stSlider label {
    font-size: 0.75rem !important;
    color: var(--text-3) !important;
  }
  h1 {
    font-weight: 600 !important;
    letter-spacing: -0.035em !important;
    color: var(--text) !important;
    font-size: 1.5rem !important;
    font-family: var(--font) !important;
  }
  .subtitle {
    color: var(--text-2) !important;
    font-size: 0.9375rem !important;
    margin-top: 0.35rem !important;
    line-height: 1.5 !important;
    max-width: 32rem !important;
    font-weight: 400 !important;
  }
  div[data-testid="stMetric"] {
    background: var(--surface) !important;
    border: 1px solid var(--line) !important;
    border-radius: 8px !important;
    padding: 1rem 1.1rem !important;
    box-shadow: none !important;
  }
  div[data-testid="stMetric"] label {
    color: var(--text-3) !important;
    font-size: 0.65rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
  }
  div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: var(--text) !important;
    font-weight: 600 !important;
  }
  .section-head {
    margin: 0 0 1.25rem 0;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--line);
  }
  .section-head-k {
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--text-3);
    font-weight: 600;
    margin: 0 0 0.35rem 0;
  }
  .section-head-t {
    font-size: 1.0625rem;
    font-weight: 600;
    color: var(--text);
    letter-spacing: -0.02em;
    margin: 0 0 0.35rem 0;
    line-height: 1.3;
  }
  .section-head-s {
    font-size: 0.8125rem;
    color: var(--text-2);
    margin: 0;
    line-height: 1.5;
    max-width: 40rem;
  }
  .md-master {
    margin-top: 0.25rem;
  }
  div[data-testid="stRadio"] > div {
    gap: 0.4rem !important;
    flex-direction: column !important;
  }
  div[data-testid="stRadio"] > div > label {
    background: var(--surface) !important;
    border: 1px solid var(--line) !important;
    border-radius: 8px !important;
    padding: 0.85rem 0.9rem 0.85rem 2.35rem !important;
    margin: 0 !important;
    transition: border-color 0.15s ease, background 0.15s ease !important;
    font-size: 0.8125rem !important;
    line-height: 1.45 !important;
    color: var(--text) !important;
    box-shadow: none !important;
  }
  div[data-testid="stRadio"] > div > label:hover {
    border-color: var(--line-strong) !important;
    background: #fafafa !important;
  }
  div[data-testid="stRadio"] > div > label:has(input:checked) {
    border-color: var(--text) !important;
    background: var(--accent-soft) !important;
  }
  .detail-shell {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 1.5rem 1.5rem;
    min-height: 420px;
    box-shadow: none;
  }
  .detail-kicker {
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--text-3);
    font-weight: 600;
    margin-bottom: 0.65rem;
  }
  .detail-title {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--text);
    line-height: 1.4;
    margin: 0 0 0.75rem 0;
    letter-spacing: -0.02em;
  }
  .detail-meta-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem 0.75rem;
    margin-bottom: 1rem;
  }
  .score-pill-lg {
    display: inline-block;
    font-size: 0.7rem;
    font-weight: 500;
    color: var(--text-2);
    background: var(--accent-soft);
    border: 1px solid var(--line);
    border-radius: 6px;
    padding: 0.2rem 0.55rem;
    letter-spacing: 0.02em;
  }
  .detail-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 0.65rem 1rem;
    margin: 1rem 0;
    font-size: 0.8125rem;
  }
  .detail-grid div span.label {
    display: block;
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-3);
    margin-bottom: 0.15rem;
  }
  .detail-grid div span.val {
    color: var(--text);
    font-weight: 500;
  }
  .detail-price {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text);
    letter-spacing: -0.03em;
  }
  .detail-bullets {
    margin: 0.75rem 0 0 1rem;
    padding: 0;
    font-size: 0.8125rem;
    color: var(--text-2);
    line-height: 1.55;
  }
  .detail-bullets li { margin-bottom: 0.35rem; }
  .detail-extras {
    margin-top: 1.1rem;
    padding-top: 1rem;
    border-top: 1px solid var(--line);
  }
  .detail-extras .extra-block { margin-bottom: 0.85rem; }
  .detail-extras .extra-block:last-child { margin-bottom: 0; }
  .detail-extras .extra-label {
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-3);
    font-weight: 600;
    margin-bottom: 0.3rem;
  }
  .detail-extras .extra-body {
    font-size: 0.8125rem;
    color: var(--text-2);
    line-height: 1.55;
    margin: 0;
  }
  .detail-extras .extra-body.muted { color: var(--text-3); font-style: normal; }
  .detail-asin {
    font-size: 0.7rem;
    color: var(--text-3);
    font-family: ui-monospace, monospace;
    margin-top: 0.65rem;
  }
  .tag-pill {
    display: inline-block;
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-2);
    background: var(--accent-soft);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 0.15rem 0.45rem;
    margin-bottom: 0;
  }
  .badge-risk {
    display: inline-block;
    font-size: 0.65rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    border-radius: 4px;
    padding: 0.2rem 0.5rem;
    border: 1px solid var(--line);
  }
  .badge-risk-low { color: #14532d; background: #f7fdf9; border-color: #bbf7d0; }
  .badge-risk-mid { color: #92400e; background: #fffbeb; border-color: #fde68a; }
  .badge-risk-high { color: #991b1b; background: #fef2f2; border-color: #fecaca; }
  .detail-ai-wrap {
    margin-top: 1.25rem;
    padding-top: 1.1rem;
    border-top: 1px solid var(--line);
  }
  .detail-ai-h {
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--text-3);
    font-weight: 600;
    margin: 0 0 0.65rem 0;
  }
  .section-label {
    font-size: 0.62rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.12em !important;
    color: var(--text-3) !important;
    font-weight: 600 !important;
    margin: 0 0 0.35rem 0 !important;
  }
  .sort-hint {
    font-size: 0.8125rem !important;
    color: var(--text-2) !important;
    margin: 0 0 1rem 0 !important;
  }
  .pcard {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 1.25rem 1.35rem;
    margin-bottom: 0.75rem;
    box-shadow: none;
    transition: border-color 0.15s ease;
  }
  .pcard:hover { border-color: var(--line-strong); }
  .pcard-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 0.75rem;
    margin-bottom: 0.65rem;
  }
  .pcard .ptitle {
    margin: 0;
    font-size: 1.0625rem;
    font-weight: 600;
    color: var(--text);
    line-height: 1.35;
    letter-spacing: -0.02em;
  }
  .pcard-stats {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 0.5rem 1.25rem;
    margin: 0.5rem 0 0.35rem 0;
    font-size: 0.8125rem;
    color: var(--text-2);
  }
  .pcard-price {
    font-size: 1.0625rem;
    font-weight: 600;
    color: var(--text);
    letter-spacing: -0.02em;
  }
  .pcard-rating { font-weight: 500; color: var(--text); }
  .pcard-opp {
    font-size: 0.75rem;
    color: var(--text-3);
    margin-top: 0.35rem;
  }
  .tag-query {
    display: inline-block;
    font-size: 0.6rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-3);
    background: transparent;
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 0.12rem 0.4rem;
    margin-bottom: 0;
  }
  .pcard-bullets {
    font-size: 0.8125rem;
    color: var(--text-2);
    margin: 0.65rem 0 0 1rem;
    padding: 0;
    line-height: 1.5;
  }
  .pcard-bullets li { margin-bottom: 0.25rem; }
  .muted-asin { color: var(--text-3); font-size: 0.68rem; font-family: ui-monospace, monospace; }
  .amo-link {
    display: inline-block;
    margin-top: 0.5rem;
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--text) !important;
    text-decoration: none !important;
    border: 1px solid var(--line);
    border-radius: 6px;
    padding: 0.35rem 0.75rem;
    background: var(--surface);
  }
  .amo-link:hover {
    background: var(--accent-soft);
    border-color: var(--line-strong);
  }
  hr.sep {
    border: none;
    border-top: 1px solid var(--line);
    margin: 2rem 0 1.5rem 0;
  }
  .stButton > button[kind="primary"] {
    border-radius: 6px !important;
    font-weight: 500 !important;
    background: var(--accent) !important;
    border: 1px solid var(--accent) !important;
    color: #fafafa !important;
    box-shadow: none !important;
  }
  .stButton > button[kind="primary"]:hover {
    background: #404040 !important;
    border-color: #404040 !important;
  }
  [data-testid="stCaptionContainer"] p,
  .stCaption {
    color: var(--text-3) !important;
  }
  /* Buyer Decision Assistant (dedicated page) */
  .copilot-hero {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 1.35rem 1.4rem;
    margin: 1.25rem 0 1rem 0;
    box-shadow: none;
  }
  .copilot-hero-kicker {
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--text-3);
    font-weight: 600;
    margin: 0 0 0.35rem 0;
  }
  .copilot-hero-title {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--text);
    letter-spacing: -0.02em;
    margin: 0 0 0.35rem 0;
    line-height: 1.25;
  }
  .copilot-hero-sub {
    font-size: 0.8125rem;
    color: var(--text-2);
    margin: 0;
    line-height: 1.55;
    max-width: 42rem;
  }
  .copilot-result-card {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 1.1rem 1.2rem;
    margin-top: 0.75rem;
    box-shadow: none;
  }
  .copilot-badge-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem 0.5rem;
    align-items: center;
    margin-bottom: 0.85rem;
  }
  .copilot-badge {
    display: inline-block;
    font-size: 0.65rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    border-radius: 4px;
    padding: 0.25rem 0.55rem;
    border: 1px solid var(--line);
  }
  .copilot-badge.rec-ok { background: #f7fdf9; color: #14532d; border-color: #bbf7d0; }
  .copilot-badge.rec-review { background: #fafafa; color: #404040; border-color: #e5e5e5; }
  .copilot-badge.rec-manual { background: #fffbeb; color: #92400e; border-color: #fde68a; }
  .copilot-badge.rec-no { background: #fef2f2; color: #991b1b; border-color: #fecaca; }
  .copilot-badge.conf-low { background: #fafafa; color: #525252; border-color: #e5e5e5; }
  .copilot-badge.conf-med { background: #f5f5f5; color: #404040; border-color: #d4d4d4; }
  .copilot-badge.conf-high { background: #f5f5f5; color: #171717; border-color: #a3a3a3; }
  .copilot-section-title {
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-3);
    font-weight: 600;
    margin: 0.85rem 0 0.35rem 0;
  }
  .copilot-section-title:first-of-type { margin-top: 0; }
  .copilot-summary {
    font-size: 0.875rem;
    color: var(--text);
    line-height: 1.55;
    margin: 0 0 0.35rem 0;
  }
  .copilot-list {
    margin: 0;
    padding-left: 1.1rem;
    font-size: 0.8125rem;
    color: var(--text-2);
    line-height: 1.5;
  }
  .copilot-list li { margin-bottom: 0.3rem; }
  /* Reserve horizontal space so titles don’t sit under the fixed menu chip */
  .main .block-container {
    padding-left: 2.75rem !important;
  }
</style>
"""


def render_sidebar_menu_button() -> None:
    """Always-visible ☰ (GPT-style) that opens the collapsed filters sidebar via the parent frame."""
    try:
        import streamlit.components.v1 as components
    except ImportError:
        return
    # Valid JS in parent document; json.dumps safely escapes for the HTML attribute.
    _js = (
        "try{var d=window.parent.document;"
        "var e=d.querySelector(" + json.dumps('[data-testid="stExpandSidebarButton"]') + ");"
        "if(e){e.click();return;}"
        "e=d.querySelector(" + json.dumps('button[aria-label="Open sidebar"]') + ");"
        "if(e){e.click();return;}"
        "var h=d.querySelector(" + json.dumps('[data-testid="stHeader"]') + ");"
        "if(h){var b=h.querySelector('button');if(b)b.click();}"
        "}catch(x){}"
    )
    components.html(
        f"""
<div style="position:fixed;top:3.35rem;left:0.85rem;z-index:10060;pointer-events:auto;">
  <button type="button" title="Open filters sidebar" aria-label="Open sidebar"
    onclick={json.dumps(_js)}
    style="background:#ffffff;border:1px solid #e8e8e8;border-radius:8px;width:40px;height:40px;cursor:pointer;
    color:#171717;display:flex;align-items:center;justify-content:center;box-shadow:0 1px 2px rgba(0,0,0,0.06);
    padding:0;margin:0;">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
    </svg>
  </button>
</div>
        """,
        height=48,
    )


def render_header():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    render_sidebar_menu_button()
    st.markdown("# TrendScout")
    st.markdown(
        '<p class="subtitle">Discover and evaluate CPG listings for retail assortment — tea, supplements, food, and more.</p>',
        unsafe_allow_html=True,
    )


def render_metrics(df: pd.DataFrame):
    n = len(df)
    avg_r = df["rating"].mean() if n else 0.0
    avg_p = df["price_num"].mean() if n and df["price_num"].notna().any() else 0.0
    max_rev = int(df["review_count"].max()) if n else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("SKUs in view", f"{n:,}")
    with c2:
        st.metric("Avg. rating", f"{avg_r:.2f}" if n else "—")
    with c3:
        st.metric("Avg. price", f"${avg_p:.2f}" if n and pd.notna(avg_p) else "—")
    with c4:
        st.metric("Max reviews", f"{max_rev:,}" if n else "—")


def format_rec_radio_label(asin: str, top5: pd.DataFrame) -> str:
    rows = top5.reset_index(drop=True)
    try:
        idx = rows["asin"].tolist().index(asin) + 1
    except ValueError:
        idx = 1
    row = rows[rows["asin"] == asin].iloc[0]
    t = str(row.get("amazon_title") or "")
    short = (t[:44] + "…") if len(t) > 46 else t
    sc = float(row.get("opportunity_score") or 0)
    risk = str(row.get("risk_level") or estimate_risk_level(row))
    return f"#{idx}  {short}\n    {sc:.0f} fit · {risk}"


def render_detail_panel(row: pd.Series) -> None:
    title = html.escape(str(row.get("amazon_title") or "—"))
    q = html.escape(str(row.get("query") or "—"))
    price = html.escape(price_display(row))
    url = str(row.get("url") or "")
    score = float(row.get("opportunity_score") or 0)
    rating = row.get("rating", "—")
    rev = int(row.get("review_count") or 0)
    rank = int(row.get("search_result_rank_used") or 0)
    asin_esc = html.escape(str(row.get("asin") or "—"))
    risk = str(row.get("risk_level") or estimate_risk_level(row))
    rb = risk_badge_class(risk)
    risk_esc = html.escape(risk)

    bullets = row.get("bullets") or []
    b_show = bullets[:3] if isinstance(bullets, list) else []
    li = "".join(f"<li>{html.escape(str(b)[:320])}</li>" for b in b_show)

    shelf_raw = row.get("product_shelf_life")
    ben_raw = row.get("product_benefits")
    shelf_s = _clean_text_field(shelf_raw) if shelf_raw is not None else ""
    ben_s = _clean_text_field(ben_raw) if ben_raw is not None else ""
    shelf_html = html.escape(shelf_s) if shelf_s else '<span class="extra-body muted">Not listed</span>'
    ben_html = html.escape(ben_s) if ben_s else '<span class="extra-body muted">Not listed</span>'
    if shelf_s:
        shelf_html = f'<p class="extra-body">{shelf_html}</p>'
    if ben_s:
        ben_html = f'<p class="extra-body">{ben_html}</p>'

    st.markdown(
        f"""
<div class="detail-shell">
  <div class="detail-kicker">Detail</div>
  <div class="detail-meta-row">
    <span class="{rb}">{risk_esc}</span>
    <span class="tag-pill">{q}</span>
    <span class="score-pill-lg">Fit score {score:.1f}</span>
  </div>
  <div class="detail-title">{title}</div>
  <div class="detail-price">{price}</div>
  <div class="detail-grid">
    <div><span class="label">Rating</span><span class="val">{rating} ★</span></div>
    <div><span class="label">Reviews</span><span class="val">{rev:,}</span></div>
    <div><span class="label">Search rank</span><span class="val">#{rank}</span></div>
  </div>
  <div class="detail-extras">
    <div class="extra-block">
      <div class="extra-label">Shelf life</div>
      {shelf_html}
    </div>
    <div class="extra-block">
      <div class="extra-label">Listing benefits</div>
      {ben_html}
    </div>
  </div>
  <div style="font-size:0.62rem;color:#737373;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.35rem;margin-top:0.85rem;font-weight:600">Highlights</div>
  <ul class="detail-bullets">{li}</ul>
  <div class="detail-asin">ASIN {asin_esc}</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    if url:
        st.link_button("View listing on Amazon", url, use_container_width=True, type="primary")


def render_recommended_block(top5: pd.DataFrame, fp: str) -> None:
    """Master-detail: ranked queue (left) + detail (right)."""
    st.markdown(
        """
<div class="section-head">
  <p class="section-head-k">Workflow</p>
  <p class="section-head-t">Priority Buying Queue</p>
  <p class="section-head-s">Top five SKUs for your current filters and <strong>sort order</strong> (see sidebar). Select a row to inspect listing detail. Open <strong>Buyer Decision Assistant</strong> from the sidebar for GPT screening.</p>
</div>
        """,
        unsafe_allow_html=True,
    )

    if top5.empty:
        st.caption("No products match the current filters.")
        return

    asins = top5["asin"].tolist()
    key = f"rec_radio_{fp}"

    c_left, c_right = st.columns([0.38, 0.62], gap="large")

    with c_left:
        st.caption("Ranked candidates")
        pick = st.radio(
            "recommended_skus",
            options=asins,
            format_func=lambda a: format_rec_radio_label(a, top5),
            label_visibility="collapsed",
            key=key,
        )

    with c_right:
        sel = top5[top5["asin"] == pick].iloc[0]
        render_detail_panel(sel)


def render_product_cards(df: pd.DataFrame, sort_key: str) -> None:
    label = SORT_LABELS.get(sort_key, sort_key)
    n = len(df)
    st.markdown('<p class="section-label">All results</p>', unsafe_allow_html=True)
    st.markdown(
        f'<p class="sort-hint">Sorted by <strong>{html.escape(label)}</strong> · {n:,} product{"s" if n != 1 else ""} in view</p>',
        unsafe_allow_html=True,
    )
    if df.empty:
        st.caption("Adjust filters to see products.")
        return

    for _, row in df.iterrows():
        bullets = row.get("bullets") or []
        b_show = bullets[:1] if isinstance(bullets, list) else []
        li = "".join(f"<li>{html.escape(str(b)[:280])}</li>" for b in b_show)
        pshow = html.escape(price_display(row))
        title = html.escape(str(row.get("amazon_title") or "—"))
        q = html.escape(str(row.get("query") or "—"))
        url = str(row.get("url") or "")
        asin = html.escape(str(row.get("asin") or "—"))
        rating = row.get("rating", "—")
        rev = int(row.get("review_count") or 0)
        sc = float(row.get("opportunity_score") or 0)
        risk = str(row.get("risk_level") or estimate_risk_level(row))
        rb = risk_badge_class(risk)
        risk_e = html.escape(risk)

        link_html = (
            f'<a class="amo-link" href="{html.escape(url)}" target="_blank" rel="noopener noreferrer">Amazon</a>'
            if url
            else ""
        )
        bullets_html = f"<ul class='pcard-bullets'>{li}</ul>" if li else ""

        st.markdown(
            f"""
<div class="pcard">
  <div class="pcard-top">
    <div>
      <span class="tag-query">{q}</span>
      <div class="ptitle">{title}</div>
    </div>
    <span class="{rb}">{risk_e}</span>
  </div>
  <div class="pcard-stats">
    <span class="pcard-price">{pshow}</span>
    <span class="pcard-rating">{rating} ★</span>
    <span>{rev:,} reviews</span>
  </div>
  <div class="pcard-opp">Fit score {sc:.1f}</div>
  <div class="muted-asin">ASIN {asin}</div>
  {bullets_html}
  {link_html}
</div>
            """,
            unsafe_allow_html=True,
        )


def main():
    st.set_page_config(
        page_title="TrendScout",
        page_icon="◆",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    df_all = load_products()
    render_header()

    if df_all.empty:
        st.stop()

    price_valid = df_all["price_num"].dropna()
    p_min_default = float(price_valid.min()) if len(price_valid) else 0.0
    p_max_default = float(price_valid.max()) if len(price_valid) else 500.0

    slider_max = max(500.0, p_max_default)
    sb = render_explore_sidebar(
        df_all,
        BENEFIT_CATEGORIES,
        p_min_default,
        p_max_default,
        slider_max,
    )
    search = sb["search"]
    q_pick = sb["q_pick"]
    benefit_pick = sb["benefit_pick"]
    min_rating = sb["min_rating"]
    pr_min = sb["pr_min"]
    pr_max = sb["pr_max"]
    sort_key = sb["sort_key"]

    filtered = apply_filters(
        df_all,
        search,
        q_pick,
        benefit_pick,
        min_rating,
        pr_min,
        pr_max,
    )
    sorted_df = sort_dataframe(filtered, sort_key)

    fp = filter_fingerprint(
        search,
        q_pick,
        benefit_pick,
        min_rating,
        pr_min,
        pr_max,
        len(filtered),
    )

    render_metrics(sorted_df)
    st.markdown('<hr class="sep"/>', unsafe_allow_html=True)

    top5 = top_recommendations(sorted_df)
    render_recommended_block(top5, fp)

    st.markdown('<hr class="sep"/>', unsafe_allow_html=True)
    render_product_cards(sorted_df, sort_key)


if __name__ == "__main__":
    main()
