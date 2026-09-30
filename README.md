# SpendSense

Turn a messy bank-statement CSV into a categorised Excel spending report, and flag the things worth acting on: subscriptions, duplicate charges and big one-off spends.

I built it because I was categorising my statement by hand every month while planning a move to Belfast on a student budget. It's a small project, but it follows the pattern I'd use for any automation: **rules where the logic is clear, AI only where it adds something, and a person reviewing anything uncertain.**

## Features

- **Cleans messy exports.** Handles `£1,200.00`, blank lines and different column names from different banks.
- **Never silently drops a row.** Rows that can't be fixed go to a *Rejected rows* sheet with the original line number and a reason.
- **Categorises cheapest-first.** Keyword rules, then previously learned rules, then Claude for whatever is left.
- **Learns over time.** Confident AI answers are saved as rules, so each month fewer merchants need AI.
- **Sends only merchant names to the AI.** No amounts, dates or balances leave your machine.
- **Works fully offline.** Without an API key, unknown merchants are just flagged for review.
- **Finds insights.** Recurring payments with their annual cost, possible duplicate charges, large one-off spends and a month-by-category summary.

## How it works

```
bank CSV ──► clean & validate ──► categorise ──► find insights ──► Excel report
             (loader.py)          (categorise.py) (insights.py)    (report.py)
```

Each transaction is categorised by the first method that knows the merchant:

| Order | Method | Source |
|---|---|---|
| 1 | Keyword rules (whole-word match) | [data/rules.json](data/rules.json) |
| 2 | Learned rules from earlier runs | `data/learned_rules.json` (created automatically) |
| 3 | Claude, in **one batched call** for all remaining merchants | [spendsense/ai.py](spendsense/ai.py) |
| 4 | Marked **Needs review** | no AI available, AI failed, or low confidence |

Money coming in that matches no rule is treated as income.

## Getting started

Requires Python 3.10 or newer. From the project folder:

```bash
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python data/make_sample.py                          # writes a fake 2-month statement
python main.py data/sample_statement.csv --no-ai    # rules only, fully offline
```

To let Claude categorise unknown merchants, set an [Anthropic API key](https://console.anthropic.com/) first:

```bash
export ANTHROPIC_API_KEY=sk-ant-...            # PowerShell: $env:ANTHROPIC_API_KEY = "sk-ant-..."
python main.py data/sample_statement.csv
```

Example output (offline mode, sample data, first run):

```
2026-08: spent £1,199.95
2026-09: spent £1,507.72
Recurring payments: 5 costing £1,295.64/year
Possible duplicate charges: 1 (check with your bank)
Large one-off spends: 1
Needs your review: 13 transactions
Rejected rows: 2
```

The Excel report is written to `output/`.

## Usage

```
python main.py STATEMENT.csv [--no-ai] [--out FOLDER]
```

| Option | Meaning |
|---|---|
| `--no-ai` | Use keyword and learned rules only; nothing is sent anywhere |
| `--out FOLDER` | Where to write the report (default: `output/`) |

**Exit codes**, so a scheduler or script can tell what happened:

| Code | Meaning |
|---|---|
| `0` | Report written |
| `1` | Input problem (file missing, or required columns missing) |
| `2` | Unexpected error (logged with a stack trace) |

### Input format

A CSV with a header row and these three columns. Common alternative names are recognised:

| Column | Also accepted | Format |
|---|---|---|
| `Date` | `Transaction Date` | `DD/MM/YYYY` |
| `Description` | `Name`, `Merchant` | free text |
| `Amount` | `Value` | negative = money out; `£ $ €` and `,` are stripped |

### The report

| Sheet | Contents |
|---|---|
| Monthly summary | Spending by category and month, with totals |
| Recurring payments | Same merchant and near-identical amount in 2+ months, with annual cost (rent excluded) |
| Possible duplicates | Same merchant, amount and day |
| Large spends | Single purchases over £100 (rent excluded) |
| Needs review | Transactions a person should check |
| All transactions | Every cleaned transaction with its category and how it was decided |
| Rejected rows | Rows that couldn't be read, with line number and reason |

## Configuration

- **Keyword rules:** edit [data/rules.json](data/rules.json). Keys are keywords matched as whole words against the description; values are categories. The first match wins, and no code changes are needed.
- **Learned rules:** `data/learned_rules.json` is written automatically. It's plain JSON, so you can inspect it, correct it or delete it to start fresh.
- **Thresholds:** the large-spend limit (£100) and recurring-amount tolerance (2%) are constants at the top of [spendsense/insights.py](spendsense/insights.py).

## AI safeguards

- **Data minimisation.** Only distinct merchant names are sent, never amounts, dates or balances. A test checks this.
- **Structured output.** Claude must return JSON matching a Pydantic schema, and the category must be one of 13 fixed values. There's no free text to parse.
- **Confidence gate.** Only `high` confidence answers become permanent rules. `medium` and `low` answers are applied but flagged for review.
- **Input treated as data.** Merchant names are passed as data to categorise. Because the output is limited to a fixed category list, a strange merchant name can at worst be miscategorised.
- **Graceful fallback.** No key, network errors, rate limits, refusals and truncated answers don't stop the run. The report is still produced and unknown merchants are flagged.

## Tests

```bash
python -m pytest -q
```

There are 23 tests, all of which run offline. Claude is replaced by a fake client, so the tests are free, fast and repeatable. They cover:

- Amount and date parsing, including rejected rows with correct line numbers.
- Whole-word rule matching.
- Only merchant names being sent to the AI.
- Learned rules being reused, so the AI isn't called again.
- Low-confidence answers being flagged and not learned.
- Network errors and refusals falling back instead of crashing.
- Recurring, duplicate and large-spend detection.

## Project structure

```
main.py                    command-line entry point, exit codes, logging
spendsense/
  loader.py                read, clean and validate the CSV
  categorise.py            rules → learned rules → Claude → needs review
  ai.py                    the Claude call (structured output, fixed categories)
  insights.py              recurring, duplicates, large spends, monthly summary
  report.py                Excel report and console summary
data/
  rules.json               keyword rules (editable without code)
  make_sample.py           fake statement generator
  sample_statement.csv     generated sample data (fictional)
tests/                     pytest suite
```

## Bugs found by running it on realistic data

- **"TFL" matched inside "NETFLIX"**, so Netflix came out as Transport. I fixed it by matching whole words only and added a regression test.
- **Rejected-row line numbers were wrong**, because rows were numbered after blank lines had been removed. Rows are now numbered first, so the numbers match the file.
- **Two coffees at Pret counted as a "subscription"** (£6.85 and £7.20 are within 5% of each other). I tightened the tolerance to 2%, since real subscriptions charge the same amount each time.

## Limitations and ideas

- Dates must be in UK `DD/MM/YYYY` format. Per-bank profiles could set the date format the same way the column aliases work.
- Recurring detection needs at least two months of data and misses subscriptions that change price.
- Learned rules are trusted once saved. A confirmation step before they become permanent would be safer.
- Each run is independent. Storing past months (for example in SQLite) would allow trend reports.
- Merchant names are normalised simply (first two words after stripping numbers and punctuation).

## License

[MIT](LICENSE) © 2026 Hassan Nazar
