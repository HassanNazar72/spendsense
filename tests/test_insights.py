# Copyright (c) 2026 Hassan Nazar. Licensed under the MIT License (see LICENSE).
import pandas as pd

from spendsense import insights


def txns(rows):
    return pd.DataFrame([
        {"date": pd.Timestamp(d), "description": m, "merchant": m, "amount": a, "category": c}
        for d, m, a, c in rows
    ])


def test_recurring_needs_two_months_and_a_stable_amount():
    df = txns([
        ("2026-08-05", "NETFLIX", -10.99, "Subscriptions"),
        ("2026-09-05", "NETFLIX", -10.99, "Subscriptions"),
        ("2026-08-04", "PRET", -6.85, "Eating Out"),   # amount varies: not a subscription
        ("2026-09-10", "PRET", -7.20, "Eating Out"),
        ("2026-09-01", "ODEON", -12.50, "Entertainment"),  # only one month
        ("2026-08-01", "RENT", -850.0, "Rent"),         # expected, excluded
        ("2026-09-01", "RENT", -850.0, "Rent"),
    ])
    result = insights.find_recurring(df)
    assert list(result["merchant"]) == ["NETFLIX"]
    assert result.loc[0, "annual_cost"] == 131.88


def test_duplicate_same_day_same_amount():
    df = txns([
        ("2026-09-09", "AMAZON", -54.99, "Shopping"),
        ("2026-09-09", "AMAZON", -54.99, "Shopping"),
        ("2026-09-10", "AMAZON", -54.99, "Shopping"),   # different day: fine
    ])
    assert len(insights.find_duplicates(df)) == 2


def test_large_spends_ignore_rent_and_income():
    df = txns([
        ("2026-09-01", "RENT", -850.0, "Rent"),
        ("2026-09-01", "STUDENT FINANCE", 1200.0, "Income"),
        ("2026-09-17", "CURRYS", -189.0, "Shopping"),
    ])
    assert list(insights.find_large_spends(df)["description"]) == ["CURRYS"]


def test_monthly_summary_totals():
    df = txns([
        ("2026-08-02", "TESCO", -20.0, "Groceries"),
        ("2026-08-03", "TFL", -5.0, "Transport"),
        ("2026-09-02", "TESCO", -30.0, "Groceries"),
    ])
    summary = insights.monthly_summary(df)
    assert summary.loc["TOTAL", "2026-08"] == 25.0
    assert summary.loc["Groceries", "2026-09"] == 30.0
