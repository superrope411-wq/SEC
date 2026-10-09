# Data dictionary

## Tables (SQLite, `data/earnings_monitor.sqlite`)

### raw_documents
One row per raw SEC response loaded, per pipeline version. `sha256` identifies the exact
bytes; `source` is `sec` or `fixture`.

### observations
Every XBRL fact in a Company Facts response, unchanged. One row per (raw document, fact).

| Column | Meaning |
|---|---|
| obs_id | Stable hash of taxonomy, concept, unit, period, value, accession and frame |
| cik, entity | Company identifiers from SEC |
| taxonomy, concept, concept_label | XBRL taxonomy (`us-gaap`, `dei`, company prefix) and concept |
| unit | `USD`, `shares`, `USD/shares`, `pure`, … |
| value | The reported number, unscaled (XBRL values are full units, not thousands) |
| period_type | `duration` (flow, has start) or `instant` (balance at a date) |
| start, end, duration_days | Period covered |
| accn, form, filed | Filing the fact came from and its filing date |
| fy, fp, frame | SEC's labels for the *filing*; not used to identify periods |

### filings
Periodic filings (10-K, 10-Q, amendments) with report date and primary document name,
from the Submissions API, supplemented from facts for older filings.

### companies, pipeline_runs
Company metadata (including SEC's `fiscalYearEnd`) and one row per run with timing,
what was downloaded vs reused, and whether reprocessing happened.

## Metric values (in memory, exports)

`MetricValue` is the unit of display. Fields: company, cik, metric_id, metric_label, unit,
scale (always "as reported"), period_type, basis (`quarter`, `annual`, `instant`, `ratio`),
period_start, period_end, period_label, value, status, concept, formula, input_values,
sources (list of `SourceRef`: obs_id, concept, unit, value, period, accn, form, filed, url),
selection_reason, notes, restated, originally_reported.

**status**: `reported` (one fact, used as is) · `derived` (computed; see formula and inputs)
· `missing` (no eligible fact; never zero) · `not_meaningful` (e.g. margin with revenue ≤ 0).

## Metrics

| id | Label | Type | Approved concepts (in order) |
|---|---|---|---|
| revenue | Revenue | duration | RevenueFromContractWithCustomerExcludingAssessedTax, Revenues, SalesRevenueNet |
| operating_income | Operating income | duration | OperatingIncomeLoss |
| net_income | Net income | duration | NetIncomeLoss |
| operating_cash_flow | Operating cash flow | duration (YTD in 10-Q) | NetCashProvidedByUsedInOperatingActivities |
| capex | Capital expenditures | duration (YTD in 10-Q) | PaymentsToAcquirePropertyPlantAndEquipment |
| cash | Cash and cash equivalents | instant | CashAndCashEquivalentsAtCarryingValue |
| debt_current | Current portion of long-term debt | instant | LongTermDebtCurrent, DebtCurrent |
| debt_noncurrent | Long-term debt | instant | LongTermDebtNoncurrent |
| accounts_receivable | Accounts receivable, net | instant | AccountsReceivableNetCurrent |
| deferred_revenue_current | Deferred revenue (current) | instant | ContractWithCustomerLiabilityCurrent, DeferredRevenueCurrent |
| deferred_revenue_noncurrent | Deferred revenue (non-current) | instant | ContractWithCustomerLiabilityNoncurrent, DeferredRevenueNoncurrent |
| assets, liabilities_and_equity | validation only | instant | Assets, LiabilitiesAndStockholdersEquity |

## Derived measures

| id | Formula | Unit |
|---|---|---|
| free_cash_flow | operating_cash_flow − capex | USD |
| operating_margin | operating_income ÷ revenue | ratio |
| net_margin | net_income ÷ revenue | ratio |
| cash_conversion | operating_cash_flow ÷ net_income | ratio |
| total_debt | debt_current + debt_noncurrent | USD |

## Comparisons

| id | Meaning | Valid for |
|---|---|---|
| sequential | this quarter vs the previous fiscal quarter | any filing |
| yoy | this quarter vs the same quarter of the prior fiscal year | any filing |
| annual | this fiscal year vs the prior fiscal year | 10-K only |

Instant metrics compare balance-sheet dates; duration metrics compare standalone quarters
(or full years). Changes in USD are absolute and percent; changes in ratios are percentage
points.
