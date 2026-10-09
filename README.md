# Quarterly Earnings Change Monitor

A research assistant for financial analysts: pull a company's SEC filings, normalize
quarterly and annual financials, compute what changed, and make every number traceable to
the filing it came from. Deterministic Python does all the math; AI (later milestones)
will only explain numbers that already carry sources.

Specification: [PROJECT_SPEC.md](PROJECT_SPEC.md). Milestone 1 (this version) is the
verified financial pipeline and dashboard with no AI.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env     # then set SEC_USER_AGENT="Your Name you@example.com"
```

SEC requires automated clients to identify themselves ([source](docs/SOURCES.md)); live
mode refuses to run without a name and email in `SEC_USER_AGENT`.

## Run

```bash
earnings-monitor ingest MSFT                 # download + cache + load (2 requests)
earnings-monitor filings MSFT                # list 10-K / 10-Q filings
earnings-monitor analyze MSFT --comparison yoy --xlsx msft.xlsx --csv msft.csv
streamlit run app/dashboard.py               # analyst dashboard
pytest                                       # 156 tests (synthetic + cached real MSFT data), offline
```

`earnings-monitor ingest MSFT --refresh` re-downloads to check for new filings.

### Offline / fixture mode

If SEC is unreachable, save real responses once (from a machine that can reach SEC):

```bash
python scripts/save_fixture.py MSFT fixtures/
```

then run with `EM_MODE=fixture EM_FIXTURE_DIR=fixtures`. Real Microsoft responses (downloaded
2026-10-09, hashes in `tests/fixtures/real/manifest.json`) are included:
`EM_MODE=fixture EM_FIXTURE_DIR=tests/fixtures/real`. Fixture mode is labeled on every
screen and in every export. It never substitutes invented numbers.

## What the dashboard shows

- Company, filing and comparison selectors (sequential quarter, same quarter last year,
  or annual for 10-Ks), with the filing date used as the as-of date.
- Financial-change table: current, prior, change, status (`reported` / `derived` /
  `missing`), with evidence for every number: XBRL concept, period, filing, EDGAR link,
  formula and inputs for derived values, and why that fact was selected.
- Findings panel driven by transparent rules with stated thresholds.
- Trend charts of standalone quarters.
- Validation tab: missing data, restatements, balance-sheet identity, YTD consistency.
- Excel workbook (Summary, Changes, Findings, Values and sources, Unresolved issues,
  Checks passed, Definitions) and CSV downloads.

## Documents

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): pipeline stages and design rules
- [docs/FACT_SELECTION_POLICY.md](docs/FACT_SELECTION_POLICY.md): how a number is chosen
- [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md): tables, fields, metrics, measures
- [docs/COMPANY_SELECTION.md](docs/COMPANY_SELECTION.md): Microsoft / Salesforce / Adobe comparability
- [docs/SOURCES.md](docs/SOURCES.md): SEC documentation checked, with quotes
- [docs/LIMITATIONS.md](docs/LIMITATIONS.md): known failure modes
- [docs/REAL_DATA_VERIFICATION.md](docs/REAL_DATA_VERIFICATION.md): Microsoft FY2025 checked against the filings
- [evaluation/](evaluation/): reference dataset, reconciliation script and workbook, golden-set scorer

## Status

Milestone 1 is verified on real data: Microsoft FY2025 (three 10-Qs and the 10-K) reconciles
200/200 against figures read independently from the filings, and dashboard and export
values match. Run `python evaluation/reconcile_msft_fy2025.py` to reproduce; details in
[docs/REAL_DATA_VERIFICATION.md](docs/REAL_DATA_VERIFICATION.md).
