# Real-data verification: Microsoft FY2025

This is the acceptance check for milestone 1: does the pipeline pick the right numbers out
of Microsoft's real SEC filings? It was run on 2026-10-09 against the official SEC data,
downloaded the same day.

**Result: 200 of 200 comparisons pass. 8 rows (short-term debt) are outside the milestone 1
metrics and are reported as NOT COVERED, not as passes.** Verification also found three
real bugs, all fixed and covered by tests (section 6).

## 1. Fiscal year under test

Microsoft's fiscal year ends June 30. FY2025 runs July 1, 2024 to June 30, 2025.

| Filing | Form | Accession | Filed | Period end |
|---|---|---|---|---|
| FY2025 Q1 | 10-Q | 0000950170-24-118967 | 2024-10-30 | 2024-09-30 |
| FY2025 Q2 | 10-Q | 0000950170-25-010491 | 2025-01-29 | 2024-12-31 |
| FY2025 Q3 | 10-Q | 0000950170-25-061046 | 2025-04-30 | 2025-03-31 |
| FY2025 | 10-K | 0000950170-25-100235 | 2025-07-30 | 2025-06-30 |

The FY2024 Q1–Q3 10-Qs (0000950170-23-054855, 0000950170-24-008814, 0000950170-24-048288)
supply only the prior-year balance-sheet dates that FY2025 year-over-year comparisons show.

## 2. How the expected answers were built (independently)

`evaluation/msft_fy2025_reference.csv` (135 rows) was typed by reading the income
statement, balance sheet and cash-flow statement pages (EDGAR "R" pages R2/R4/R6) of the
filings above. Each row has the accession, period, line item, value in millions as printed,
and the URL of the page it was read from. **No code from this project produced those
numbers.** Before use, the reference passed its own checks: total assets equal total
liabilities and equity on all 8 balance-sheet dates, and each three-month cash-flow column
equals the difference of the year-to-date columns.

## 3. The data the pipeline ran on

`tests/fixtures/real/` holds the unmodified responses from SEC's two APIs, gzip-compressed:

| File | Source URL | SHA-256 of the bytes SEC returned |
|---|---|---|
| `submissions/CIK0000789019.json.gz` | https://data.sec.gov/submissions/CIK0000789019.json | `2484a2a3…3139c` |
| `companyfacts/CIK0000789019.json.gz` | https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json | `f8aae296…7246f` |

`manifest.json` records the full hashes, download time (2026-10-09T18:21:33Z) and the
User-Agent used. `tests/test_real_msft.py::test_fixture_files_match_manifest` re-checks
the hashes on every test run, so the cached files can't drift silently.

## 4. Tolerances

| Kind | Pass if | Why |
|---|---|---|
| USD amounts | \|actual − expected\| ≤ $500,000 | Statements print millions; XBRL stores whole dollars. Anything within half a million is the same printed number. |
| Ratios (margins, conversion) | \|actual − expected\| ≤ 0.0001 (0.01 pp) | Expected ratios are computed from the printed millions, so they carry rounding. |

A missing or "not meaningful" pipeline value always fails. Any source fact filed after the
analysis date also fails (look-ahead).

## 5. What was checked and the result

Run `python evaluation/reconcile_msft_fy2025.py`. It writes
`evaluation/MSFT_FY2025_reconciliation.xlsx` (sheets: Summary, Reconciliation, Provenance,
Reference checks, Export match, Reference dataset) and `evaluation/MSFT_FY2025_reconciliation.md`.

| Section | What it checks | Pass |
|---|---|---|
| Reported | Every reference line item (revenue, operating income, net income, operating cash flow, capex, cash, receivables, current and non-current deferred revenue, current and long-term debt, total assets, liabilities and equity), selected as of that filing's date | 127 / 127 |
| Displayed quarter | Standalone Q2 and Q3 values shown by the dashboard equal the statement's three-month column (and the YTD difference) | 10 / 10 |
| Derived Q4 | FY2025 Q4 and FY2024 Q4 = annual (10-K) − nine months (Q3 10-Q), for all five flow metrics | 10 / 10 |
| Derived measure | Free cash flow, operating margin, net margin and cash conversion for each FY2025 quarter, Q4 and both full years; total debt at each quarter end | 29 / 29 |
| Displayed prior instant | Prior-year balance-sheet values shown in year-over-year comparisons | 24 / 24 |
| Not covered | Short-term debt (commercial paper), outside milestone 1 metrics | 8 rows, not counted |

Selected FY2025 figures (USD millions, all PASS):

| | Q1 | Q2 | Q3 | Q4 (derived) | FY2025 |
|---|---|---|---|---|---|
| Revenue | 65,585 | 69,632 | 70,066 | 76,441 | 281,724 |
| Operating income | 30,552 | 31,653 | 32,000 | 34,323 | 128,528 |
| Net income | 24,667 | 24,108 | 25,824 | 27,233 | 101,832 |
| Operating cash flow | 34,180 | 22,291 | 37,044 | 42,647 | 136,162 |
| Capital expenditures | 14,923 | 15,804 | 16,745 | 17,079 | 64,551 |

Items from the request, one by one:

- **Units and signs.** All values are USD, whole dollars; capex is a positive outflow as on
  the statement; free cash flow = OCF − capex.
- **Reporting periods.** Every comparison matches exact start and end dates, never the
  `fy`/`fp` labels.
- **Consolidated vs segment.** Company Facts contains only non-dimensional (consolidated)
  facts; every selected source is the consolidated line item on R2/R4/R6.
- **Standalone quarterly cash flow and Q4.** Microsoft prints three-month cash-flow columns
  in its 10-Qs, so Q2 and Q3 cash flow are *reported*; the reconciliation also checks them
  against nine-month minus six-month figures. Q4 is *derived* (FY − 9M) and its two inputs
  are the 10-K and the Q3 10-Q, both shown with links.
- **Historical availability.** 247 source facts behind the reconciled values were checked:
  every one was filed on or before the date of the filing being analyzed (0 violations).
- **Amendments and restatements.** See section 7: real cases exist in Microsoft's history
  and are now regression tests. FY2025 itself has no restated consolidated figures in later
  filings.
- **Dashboard and exports.** 205 values exported by the 10 FY2025 analyses (each filing ×
  each comparison) were matched to the reconciled values by metric and exact period: all
  equal, all with sources. `tests/test_dashboard_real.py` drives the Streamlit app on the
  real data, picks the FY2025 10-K annual comparison, and checks the rendered table.

## 6. Discrepancies found and fixed

1. **The export module was missing from the repository.** `.gitignore` had `exports/`,
   meant for output files, which also matched the source folder
   `src/earnings_monitor/exports/`. The code worked on the machine that built it but was
   never committed, so a fresh checkout could not run the CLI, dashboard or tests. Fixed by
   anchoring the rule to `/exports/` and restoring `exports/tables.py`.
2. **Filings before October 2020 could not be analyzed.** SEC's submissions file lists only
   the most recent filings; older ones come from the facts file, where the code took the
   period end as the latest date in the filing. That latest date was the cover-page share
   count (e.g. 2020-07-27), not the balance-sheet date (2020-06-30), so all 44 older 10-K/10-Qs
   failed with "not a known fiscal quarter end". Fixed by using only financial-statement
   (`us-gaap`) facts for the period end. Now all 68 Microsoft filings back to 2009 load.
3. **The reconciliation's dashboard/export check matched rows by label prefix**, which
   could pair a quarter with the full year ending the same day (41 false mismatches). It
   now matches by metric id and exact period dates and also checks the Changes sheet.

None of the FY2025 numbers were wrong; fixes 1 and 2 affected whether the app ran at all.

## 7. Real restatement and amendment cases (beyond FY2025)

- **ASC 606 restatement (FY2017 revenue).** The FY2017 Q1 10-Q (filed 2016-10-20)
  reported revenue of $20,453M. After adopting the new revenue standard, the FY2018 Q1 10-Q
  (filed 2017-10-26) restated the same quarter to $21,928M. As of 2016-10-20 the pipeline
  shows $20,453M; as of 2017-10-26 it shows $21,928M, marked restated, with the original
  value kept. The later number does not leak backwards.
- **FY2016 net income restatement.** The FY2016 Q3 10-Q restated Q1 and Q2 net income
  (4,620 → 4,902 and 4,998 → 5,018) but did not re-tag the six-month total, which remains
  9,618. The displayed quarters are correct, and the YTD consistency check correctly
  raises an error that nine months minus the (stale) six months does not equal the reported
  Q3. This is the intended behavior: the analyst sees the inconsistency instead of a
  silently mixed number.
- **Amendment.** For FY2012 Q2 the only XBRL source is the 10-Q/A filed 2012-01-27; the
  pipeline uses it and shows the form as 10-Q/A.

## 8. Whole-history scan (not a pass/fail test)

All 68 Microsoft 10-K/10-Q filings were analyzed with every valid comparison (153 runs, no
crashes). The gaps found are shown as *missing*, never filled in:

- **Operating cash flow, FY2014–FY2018.** Microsoft tagged it
  `NetCashProvidedByUsedInOperatingActivitiesContinuingOperations` in those years. That
  concept excludes discontinued operations, so it is not on the approved list; adding it
  safely needs a check that discontinued operations are zero. Left for a later decision.
- **Current portion of long-term debt, FY2009–FY2012**: not tagged with an approved concept.

## 9. Speed

On the cloud test machine: first load of Microsoft's 32,671 facts ≈ 2 s; a reload of
unchanged data ≈ 0.9 s (skipped by hash); the full reconciliation ≈ 26 s; the whole test
suite (156 tests) ≈ 45 s. No API cost: SEC's APIs are free and only two requests are made.

## 10. What remains unverified

- Salesforce and Adobe (milestone 3).
- The YTD-subtraction path for Q2/Q3 is exercised on real data only for Q4, because
  Microsoft prints three-month cash-flow columns; Q2/Q3 YTD subtraction is covered by
  synthetic tests.
- An amendment that changes numbers (the FY2012 10-Q/A matches later filings).
