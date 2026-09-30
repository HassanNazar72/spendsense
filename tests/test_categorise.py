# Copyright (c) 2026 Hassan Nazar. Licensed under the MIT License (see LICENSE).
"""Categoriser tests. Claude is replaced by a fake client, so these run offline and cost nothing."""

import json
from types import SimpleNamespace

import anthropic
import httpx
import pandas as pd
import pytest

from spendsense.ai import Guesses, MerchantGuess
from spendsense.categorise import NEEDS_REVIEW, categorise


class FakeClaude:
    """Stands in for anthropic.Anthropic(); records what we would have sent."""

    def __init__(self, guesses=None, stop_reason="end_turn", error=None):
        self.calls = []
        self._guesses, self._stop_reason, self._error = guesses or [], stop_reason, error
        self.messages = SimpleNamespace(parse=self._parse)

    def _parse(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        parsed = Guesses(results=self._guesses) if self._stop_reason == "end_turn" else None
        return SimpleNamespace(stop_reason=self._stop_reason, parsed_output=parsed)


@pytest.fixture
def paths(tmp_path):
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps({"TFL": "Transport", "TESCO": "Groceries"}))
    return {"rules_path": rules, "learned_path": tmp_path / "learned.json"}


def txns(*rows):
    return pd.DataFrame(
        [{"date": pd.Timestamp("2026-09-01"), "description": d, "merchant": m, "amount": a} for d, m, a in rows]
    )


def test_rule_matches_whole_words_only(paths):
    # Regression: "TFL" used to match inside "NETFLIX".
    df, _ = categorise(txns(("NETFLIX.COM", "NETFLIX COM", -10.99), ("TFL TRAVEL CH", "TFL TRAVEL", -8.1)),
                       use_ai=False, **paths)
    assert list(df["category"]) == [NEEDS_REVIEW, "Transport"]


def test_money_in_without_rule_is_income(paths):
    df, _ = categorise(txns(("REFUND FROM FRIEND", "REFUND FROM", 20.0)), use_ai=False, **paths)
    assert df.loc[0, "category"] == "Income"


def test_claude_only_sees_unknown_merchant_names(paths):
    fake = FakeClaude([MerchantGuess(merchant="PUREGYM LTD", category="Health & Fitness", confidence="high")])
    categorise(txns(("TESCO STORES", "TESCO STORES", -23.45), ("PUREGYM LTD", "PUREGYM LTD", -24.99)),
               client=fake, **paths)

    sent = fake.calls[0]["messages"][0]["content"]
    assert "PUREGYM LTD" in sent
    assert "TESCO" not in sent      # already known by rules: not sent
    assert "24.99" not in sent      # amounts never leave the machine


def test_confident_answers_become_learned_rules(paths):
    fake = FakeClaude([MerchantGuess(merchant="PUREGYM LTD", category="Health & Fitness", confidence="high")])
    df, stats = categorise(txns(("PUREGYM LTD", "PUREGYM LTD", -24.99)), client=fake, **paths)
    assert df.loc[0, "category"] == "Health & Fitness"
    assert stats["new_rules_learned"] == 1

    # Next month: same merchant is handled by the learned rule, Claude isn't called.
    fake_next = FakeClaude()
    df2, _ = categorise(txns(("PUREGYM LTD", "PUREGYM LTD", -24.99)), client=fake_next, **paths)
    assert df2.loc[0, "source"] == "learned"
    assert fake_next.calls == []


def test_low_confidence_is_flagged_for_review_and_not_learned(paths):
    fake = FakeClaude([MerchantGuess(merchant="XYZ LTD", category="Shopping", confidence="low")])
    df, stats = categorise(txns(("XYZ LTD 123", "XYZ LTD", -5.0)), client=fake, **paths)
    assert df.loc[0, "needs_review"]
    assert stats["new_rules_learned"] == 0


@pytest.mark.parametrize("fake", [
    FakeClaude(error=anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))),
    FakeClaude(stop_reason="refusal"),
])
def test_ai_failure_falls_back_instead_of_crashing(paths, fake):
    df, stats = categorise(txns(("PUREGYM LTD", "PUREGYM LTD", -24.99)), client=fake, **paths)
    assert df.loc[0, "category"] == NEEDS_REVIEW
    assert stats["ai_error"]
