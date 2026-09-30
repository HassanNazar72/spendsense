# Copyright (c) 2026 Hassan Nazar. Licensed under the MIT License (see LICENSE).
import pandas as pd
import pytest

from spendsense.loader import load_statement, normalise_merchant, parse_amount


@pytest.mark.parametrize("raw, expected", [
    ("-23.45", -23.45),
    ("£1,200.00", 1200.0),
    (" -8.10 ", -8.10),
    ("abc", None),
    (None, None),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


@pytest.mark.parametrize("description, expected", [
    ("TESCO STORES 3021 LONDON", "TESCO STORES"),
    ("UBER *TRIP HELP.UBER.COM", "UBER TRIP"),
    ("SAINSBURYS S/MKT 0877", "SAINSBURYS MKT"),
    ("NETFLIX.COM", "NETFLIX COM"),
])
def test_normalise_merchant_groups_same_shop(description, expected):
    assert normalise_merchant(description) == expected


def write_csv(tmp_path, text):
    path = tmp_path / "statement.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_bad_rows_are_rejected_with_reason_and_line_number(tmp_path):
    path = write_csv(tmp_path, (
        "Date,Description,Amount\n"
        "01/09/2026,TESCO,-10.00\n"   # line 2: fine
        ",,\n"                          # line 3: blank, skipped silently
        "32/09/2026,TESCO,-5.00\n"    # line 4: impossible date
        "02/09/2026,PRET,abc\n"       # line 5: bad amount
    ))
    clean, rejected = load_statement(path)

    assert len(clean) == 1
    assert list(rejected["source_row"]) == [4, 5]
    assert list(rejected["reason"]) == ["invalid date", "invalid amount"]


def test_column_aliases_from_other_banks(tmp_path):
    path = write_csv(tmp_path, "Transaction Date,Merchant,Value\n01/09/2026,TESCO,-10.00\n")
    clean, _ = load_statement(path)
    assert clean.loc[0, "amount"] == -10.0
    assert clean.loc[0, "date"] == pd.Timestamp("2026-09-01")


def test_missing_column_raises_clear_error(tmp_path):
    path = write_csv(tmp_path, "Date,Description\n01/09/2026,TESCO\n")
    with pytest.raises(ValueError, match="amount"):
        load_statement(path)
