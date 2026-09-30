# Copyright (c) 2026 Hassan Nazar. Licensed under the MIT License (see LICENSE).
"""Load and clean a bank statement CSV.

Bank exports are messy: currency symbols, thousand separators, blank lines,
occasional corrupt rows. We clean what we can and *report* what we can't -
a bad row is never silently dropped.
"""

import re
from pathlib import Path

import pandas as pd

# Different banks name the same column differently. Map them all to one schema.
COLUMN_ALIASES = {
    "date": "date", "transaction date": "date",
    "description": "description", "name": "description", "merchant": "description",
    "amount": "amount", "value": "amount",
}
REQUIRED = ["date", "description", "amount"]


def parse_amount(raw) -> float | None:
    """'£1,200.00' -> 1200.0, '-23.45' -> -23.45, 'abc' -> None."""
    if raw is None or pd.isna(raw):
        return None
    text = re.sub(r"[£$€,\s]", "", str(raw))
    try:
        return float(text)
    except ValueError:
        return None


def normalise_merchant(description: str) -> str:
    """'TESCO STORES 3021 LONDON' -> 'TESCO STORES'; 'UBER *TRIP HELP.UBER.COM' -> 'UBER TRIP'.

    Strips store numbers and punctuation and keeps the first two words, so the
    same shop groups together however the bank formats the line.
    """
    text = re.sub(r"[^A-Z ]", " ", str(description).upper())
    words = [w for w in text.split() if len(w) > 1]  # drop stray letters like the S in S/MKT
    return " ".join(words[:2])


def load_statement(path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (clean transactions, rejected rows with a reason)."""
    raw = pd.read_csv(path, dtype=str, skip_blank_lines=True)
    raw.columns = [COLUMN_ALIASES.get(c.strip().lower(), c.strip().lower()) for c in raw.columns]

    missing = [c for c in REQUIRED if c not in raw.columns]
    if missing:
        raise ValueError(f"Statement is missing required columns: {missing}")

    # Record the original line number *before* dropping blank lines, so a rejected
    # row can be found in the source file. +2 = header line + 1-based numbering.
    raw["source_row"] = raw.index + 2
    raw = raw.dropna(how="all", subset=REQUIRED)

    raw["parsed_date"] = pd.to_datetime(raw["date"], format="%d/%m/%Y", errors="coerce")
    raw["parsed_amount"] = raw["amount"].map(parse_amount)

    reasons = pd.Series("", index=raw.index)
    reasons[raw["parsed_date"].isna()] += "invalid date; "
    reasons[raw["parsed_amount"].isna()] += "invalid amount; "
    reasons[raw["description"].fillna("").str.strip() == ""] += "missing description; "

    bad = reasons != ""
    rejected = raw.loc[bad, ["source_row", "date", "description", "amount"]].copy()
    rejected["reason"] = reasons[bad].str.rstrip("; ")

    clean = raw.loc[~bad].copy()
    clean = pd.DataFrame({
        "date": clean["parsed_date"],
        "description": clean["description"].str.strip(),
        "merchant": clean["description"].map(normalise_merchant),
        "amount": clean["parsed_amount"].astype(float),
    }).sort_values("date").reset_index(drop=True)

    return clean, rejected.reset_index(drop=True)
