# Copyright (c) 2026 Hassan Nazar. Licensed under the MIT License (see LICENSE).
"""Turn categorised transactions into things worth acting on."""

import pandas as pd

LARGE_SPEND_THRESHOLD = 100.0     # a single purchase above this gets flagged
RECURRING_AMOUNT_TOLERANCE = 0.02  # amounts within 2% count as "the same" payment


def spending(df: pd.DataFrame) -> pd.DataFrame:
    """Money out only, as positive numbers."""
    out = df[df["amount"] < 0].copy()
    out["spent"] = -out["amount"]
    out["month"] = out["date"].dt.strftime("%Y-%m")
    return out


def monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Category x month table of spending, with a total row."""
    table = spending(df).pivot_table(
        index="category", columns="month", values="spent", aggfunc="sum", fill_value=0
    ).round(2)
    table.loc["TOTAL"] = table.sum()
    return table


def find_recurring(df: pd.DataFrame) -> pd.DataFrame:
    """Same merchant, roughly the same amount, in 2+ different months.

    Rent is excluded: it's expected, and it would drown out the subscriptions
    and bills that are actually worth reviewing.
    """
    rows = []
    spent = spending(df)
    for merchant, group in spent[spent["category"] != "Rent"].groupby("merchant"):
        months = group["month"].nunique()
        avg = group["spent"].mean()
        spread = group["spent"].max() - group["spent"].min()
        if months >= 2 and spread <= avg * RECURRING_AMOUNT_TOLERANCE:
            rows.append({
                "merchant": merchant,
                "category": group["category"].iloc[0],
                "monthly_cost": round(avg, 2),
                "annual_cost": round(avg * 12, 2),
                "months_seen": months,
            })
    result = pd.DataFrame(rows, columns=["merchant", "category", "monthly_cost", "annual_cost", "months_seen"])
    return result.sort_values("annual_cost", ascending=False).reset_index(drop=True)


def find_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Identical merchant + amount on the same day: possibly charged twice."""
    spent = spending(df)
    dupes = spent[spent.duplicated(["date", "merchant", "amount"], keep=False)]
    return dupes[["date", "description", "spent"]].reset_index(drop=True)


def find_large_spends(df: pd.DataFrame, threshold: float = LARGE_SPEND_THRESHOLD) -> pd.DataFrame:
    """One-off big purchases (rent is expected, so it's excluded)."""
    spent = spending(df)
    large = spent[(spent["spent"] > threshold) & (spent["category"] != "Rent")]
    return large[["date", "description", "category", "spent"]].reset_index(drop=True)
