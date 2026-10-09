# Fact selection policy

This document says exactly how one number gets from an SEC filing to the dashboard, and
why. Every rule here is enforced in `src/earnings_monitor/financial_normalization/` and
tested in `tests/test_normalization.py`.

## 1. Where facts come from

All facts come from SEC's XBRL **Company Facts** API
(`https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`), which returns every
numeric fact a company has filed in XBRL, tagged with concept, unit, period, form, filing
date and accession number. The filing list comes from the **Submissions** API. Both are
documented at https://www.sec.gov/search-filings/edgar-application-programming-interfaces.

Every fact in that file is stored unchanged as an *observation* (table `observations`), so
the original data is always available next to the normalized selection.

## 2. What makes a fact eligible

A fact is eligible for a metric and period only if **all** of the following hold:

| Rule | Why |
|---|---|
| Filed on or before the **as-of date** (the selected filing's date) | A historical analysis must only use what an analyst could have seen at the time. Later restatements must not leak backwards. |
| Form is 10-K, 10-Q or an amendment of one | Other forms (8-K, S-1, proxy) are out of scope. |
| Taxonomy is `us-gaap` and the concept is on the metric's approved list | A tag name alone is not enough: the list is curated per metric and ordered by preference. Company-specific extension concepts are not used in milestone 1; if a company reports a metric only under its own extension, the metric shows as missing with a note. |
| Unit is `USD` | Prevents mixing shares, ratios or foreign currencies. |
| Period type matches (duration vs instant) | Balance-sheet items are point-in-time; income and cash-flow items are flows. |
| Period dates match **exactly** | Durations must match both start and end; instants must match the end date. We never match on `fy`/`fp` labels (see section 4). |

Company Facts contains only non-dimensional facts, so every eligible fact is a consolidated
total, never a segment or a member of a breakdown.

## 3. Choosing among eligible facts

1. Concepts are tried in the approved order. The first concept with any eligible fact wins.
   If a lower-ranked concept disagrees, a warning is recorded.
2. Among facts for the winning concept and exact period, the one from the **most recently
   filed** eligible filing is used. The earliest value is also kept; if they differ the
   value is flagged **restated** and both values are shown.
3. If a single filing contains two different values for the same concept and period, an
   error is raised for manual review.
4. The selection reason (concept rank, unit, period, filing, number of filings seen,
   restatement) is stored with the value and shown in the dashboard and exports.

## 4. Period normalization

**Fiscal calendar.** Fiscal years are detected from annual-length (350–380 day) duration
facts in 10-K filings; quarter ends are the distinct end dates of year-to-date facts that
start on the fiscal-year start. The company's own fiscal-year number is taken from the `fy`
field of the filing *whose own period* falls in that year. This handles June year-ends
(Microsoft), January year-ends (Salesforce), November year-ends (Adobe) and 52/53-week years.

**Why not `fy`/`fp`?** In Company Facts those fields describe the filing a fact came from,
not the period the fact covers: a prior-year comparative inside a FY2025 Q2 10-Q is also
tagged `fy=2025, fp=Q2`. Using dates avoids mislabeling comparatives.

**Standalone quarters.**
- If a 3-month fact exists for the quarter, it is used as *reported*.
- Otherwise the quarter is *derived* as `YTD(this quarter) − YTD(previous quarter)`, only
  when both facts use the **same concept** and the **same fiscal-year start**.
- Q4 is never filed on its own, so it is derived as `FY − YTD through Q3` under the same
  conditions.
- Cash-flow statements are reported year-to-date in 10-Qs, so quarterly cash flow is
  usually derived.
- A derived value carries its formula, both inputs and both source filings.

**Balance-sheet (instant) values** are read at the quarter-end date; no subtraction.

## 5. Derived measures

| Measure | Formula | Not meaningful when |
|---|---|---|
| Free cash flow | Operating cash flow − Capital expenditures | an input is missing |
| Operating margin | Operating income ÷ Revenue | revenue ≤ 0 |
| Net margin | Net income ÷ Revenue | revenue ≤ 0 |
| Cash-flow conversion | Operating cash flow ÷ Net income | net income ≤ 0 |
| Total debt | Current portion of long-term debt + Long-term debt | an input is missing |

Changes in USD metrics are absolute and percent (percent only when the prior value is
positive). Changes in ratios are in percentage points.

## 6. Missing data

A metric with no eligible fact is shown as **missing**, with a note saying which concepts
were looked for and the as-of date. It is never shown as zero.

## 7. Known limitations

- Company-specific extension concepts are ignored.
- Short-term borrowings and commercial paper are not part of "debt".
- Only the first approved concept with data is used; if a company switches concepts
  between years, the change is flagged but values are not spliced.
- 10-K/A and 10-Q/A amendments are eligible like originals; an amendment that changes a
  value will show as a restatement.
