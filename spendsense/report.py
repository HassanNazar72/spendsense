# Copyright (c) 2026 Hassan Nazar. Licensed under the MIT License (see LICENSE).
"""Write the Excel report and a short text summary."""

from datetime import datetime
from pathlib import Path

import pandas as pd

from spendsense import insights


def build_report(df: pd.DataFrame, rejected: pd.DataFrame, out_dir: Path) -> tuple[Path, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"spending_report_{datetime.now():%Y%m%d_%H%M%S}.xlsx"

    summary = insights.monthly_summary(df)
    recurring = insights.find_recurring(df)
    duplicates = insights.find_duplicates(df)
    large = insights.find_large_spends(df)
    review = df[df["needs_review"]]

    transactions = df.assign(date=df["date"].dt.date)
    with pd.ExcelWriter(path, engine="openpyxl") as xl:
        summary.to_excel(xl, sheet_name="Monthly summary")
        recurring.to_excel(xl, sheet_name="Recurring payments", index=False)
        duplicates.assign(date=duplicates["date"].dt.date).to_excel(xl, sheet_name="Possible duplicates", index=False)
        large.assign(date=large["date"].dt.date).to_excel(xl, sheet_name="Large spends", index=False)
        review.assign(date=review["date"].dt.date).to_excel(xl, sheet_name="Needs review", index=False)
        transactions.to_excel(xl, sheet_name="All transactions", index=False)
        rejected.to_excel(xl, sheet_name="Rejected rows", index=False)
        for sheet in xl.sheets.values():  # readable column widths
            for col in sheet.columns:
                sheet.column_dimensions[col[0].column_letter].width = 22

    lines = ["SpendSense summary", "=" * 40]
    for month in summary.columns:
        lines.append(f"{month}: spent £{summary.loc['TOTAL', month]:,.2f}")
    if not recurring.empty:
        lines.append(f"Recurring payments: {len(recurring)} costing £{recurring['annual_cost'].sum():,.2f}/year")
    if not duplicates.empty:
        groups = len(duplicates.drop_duplicates())
        lines.append(f"Possible duplicate charges: {groups} (check with your bank)")
    if not large.empty:
        lines.append(f"Large one-off spends: {len(large)}")
    lines.append(f"Needs your review: {len(review)} transactions")
    lines.append(f"Rejected rows: {len(rejected)}")
    return path, "\n".join(lines)
