# Copyright (c) 2026 Hassan Nazar. Licensed under the MIT License (see LICENSE).
"""SpendSense command line.

    python main.py data/sample_statement.csv          # rules + Claude (if ANTHROPIC_API_KEY is set)
    python main.py data/sample_statement.csv --no-ai  # rules only, no data leaves your machine

Exit codes (so schedulers and other tools can tell what happened):
    0 = report written, 1 = input file problem, 2 = unexpected error
"""

import argparse
import logging
import sys
from pathlib import Path

from spendsense.categorise import categorise
from spendsense.loader import load_statement
from spendsense.report import build_report

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def main() -> int:
    parser = argparse.ArgumentParser(description="Categorise a bank statement CSV and produce a spending report.")
    parser.add_argument("statement", type=Path, help="Path to the bank statement CSV")
    parser.add_argument("--no-ai", action="store_true", help="Use keyword rules only")
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR, help="Folder for the Excel report")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # so £ prints correctly on Windows consoles

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("spendsense")

    try:
        transactions, rejected = load_statement(args.statement)
    except (FileNotFoundError, ValueError) as exc:
        log.error("Could not read statement: %s", exc)
        return 1

    try:
        log.info("Loaded %d transactions (%d rejected rows)", len(transactions), len(rejected))
        categorised, stats = categorise(transactions, use_ai=not args.no_ai)
        log.info("Categorised by: %s | sent to AI: %d merchants | new rules learned: %d",
                 stats["by_source"], stats["merchants_sent_to_ai"], stats["new_rules_learned"])
        path, summary = build_report(categorised, rejected, args.out)
    except Exception:
        log.exception("Unexpected error")
        return 2

    print(summary)
    print(f"\nReport: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
