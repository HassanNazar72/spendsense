# Copyright (c) 2026 Hassan Nazar. Licensed under the MIT License (see LICENSE).
"""Categorise transactions: rules first, Claude only for what the rules miss.

Order of precedence:
  1. Keyword rules (data/rules.json)        - free, instant, predictable
  2. Learned rules (data/learned_rules.json) - answers Claude gave confidently before
  3. Claude, in one batched call             - only for merchants still unknown
  4. 'Needs review'                          - if there's no AI or it failed
"""

import json
import logging
import os
import re
from pathlib import Path

import anthropic
import pandas as pd

from spendsense.ai import AIUnavailable, categorise_with_claude

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RULES_PATH = DATA_DIR / "rules.json"
LEARNED_PATH = DATA_DIR / "learned_rules.json"
NEEDS_REVIEW = "Needs review"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def match_rule(description: str, merchant: str, rules: dict, learned: dict) -> tuple[str | None, str]:
    upper = description.upper()
    for keyword, category in rules.items():
        # Whole words only: a plain substring check matched "TFL" inside "NETFLIX".
        if re.search(rf"\b{re.escape(keyword)}\b", upper):
            return category, "rule"
    if merchant in learned:
        return learned[merchant], "learned"
    return None, ""


def ai_available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def categorise(
    df: pd.DataFrame,
    use_ai: bool = True,
    client: anthropic.Anthropic | None = None,
    rules_path: Path = RULES_PATH,
    learned_path: Path = LEARNED_PATH,
) -> tuple[pd.DataFrame, dict]:
    """Add category / source / needs_review columns. Returns (df, run stats)."""
    rules = load_json(rules_path)
    learned = load_json(learned_path)
    df = df.copy()

    matches = [match_rule(d, m, rules, learned) for d, m in zip(df["description"], df["merchant"])]
    df["category"] = [c for c, _ in matches]
    df["source"] = [s for _, s in matches]
    df["needs_review"] = False

    # Money coming in with no rule is almost always a transfer or income.
    unmatched_income = df["category"].isna() & (df["amount"] > 0)
    df.loc[unmatched_income, ["category", "source"]] = ["Income", "rule"]

    unknown = sorted(df.loc[df["category"].isna(), "merchant"].unique())
    stats = {"merchants_sent_to_ai": 0, "new_rules_learned": 0, "ai_error": None}

    if unknown and use_ai and (client is not None or ai_available()):
        try:
            guesses = categorise_with_claude(unknown, client=client)
            stats["merchants_sent_to_ai"] = len(unknown)
            new_rules = {}
            for merchant, guess in guesses.items():
                rows = df["merchant"] == merchant
                df.loc[rows, ["category", "source"]] = [guess.category, "claude"]
                if guess.confidence == "high" and guess.category != "Other":
                    new_rules[merchant] = guess.category
                else:
                    df.loc[rows, "needs_review"] = True  # a person should check this one
            if new_rules:
                learned.update(new_rules)
                learned_path.write_text(json.dumps(learned, indent=2, sort_keys=True), encoding="utf-8")
                stats["new_rules_learned"] = len(new_rules)
        except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.APIStatusError, AIUnavailable) as exc:
            # The report still gets produced; unknown merchants are flagged instead.
            log.warning("AI categorisation failed, falling back to rules only: %s", exc)
            stats["ai_error"] = str(exc)

    still_unknown = df["category"].isna()
    df.loc[still_unknown, ["category", "source", "needs_review"]] = [NEEDS_REVIEW, "none", True]

    stats["by_source"] = df["source"].value_counts().to_dict()
    return df, stats
