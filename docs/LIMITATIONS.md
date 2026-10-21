# Limitations and known failure modes

- **Verified on one fiscal year per company.** Microsoft FY2025 reconciles 200/200,
  Salesforce FY2026 422/422 and Adobe FY2025 452/452 against figures read from the filings
  ([REAL_DATA_VERIFICATION.md](REAL_DATA_VERIFICATION.md)). Other years are computed by the
  same code but not reconciled; Microsoft FY2026, for example, is shown in the dashboard
  without having been checked line by line.
- **Company-specific tagging is handled case by case.** Adobe's debt concepts needed an
  override; a fourth company could need others, and the reconciliation is how they are found.
- **Cross-company periods never match.** The comparison view always shows the offset and
  compares only each company's own growth and ratios, but the windows still differ by about
  a month, and a fiscal-year comparison covers only about seven common months.
- **Operating cash flow tagged as "continuing operations" is not used.** Microsoft used
  `NetCashProvidedByUsedInOperatingActivitiesContinuingOperations` in FY2014–FY2018, so
  operating cash flow, free cash flow and cash conversion show as missing for those years.
- **Only standard `us-gaap` concepts.** Company extension concepts are ignored; a metric a
  company reports only under its own tag shows as missing.
- **Concept lists are curated, not exhaustive.** If a company uses an unexpected tag (for
  example for capital expenditures), the value is missing with a note rather than guessed.
- **Debt is partial.** Commercial paper and short-term borrowings are not included.
- **Deferred revenue comparability** across companies depends on each company's tagging and
  is flagged, not resolved.
- **Derived quarters inherit restatements.** A Q4 derived from a 10-K and a Q3 10-Q uses the
  latest values available as of the as-of date; if the 10-K restated nine-month figures and
  the restated YTD was not re-tagged, the derived Q4 could be off. The two source facts are
  always shown so this can be checked. Real example: Microsoft's FY2016 Q3 10-Q adjusted
  Q1 and Q2 net income for a new share-based payment accounting standard without re-tagging the six-month total; the YTD consistency check
  reports this as an error rather than hiding it.
- **Revision detection is value-based and does not know the reason.** A value that changed in a
  later filing is flagged "revised" whether the cause was a new accounting standard or an
  error correction; the filing text says which. A change that only appears in an
  amendment's text (not XBRL) is not seen.
- **Fiscal calendar detection needs 10-K data.** A company with fewer than one full fiscal
  year of XBRL filings will not get a calendar.
- **Submissions "recent" list** can omit very old filings; those are added from facts but
  without a primary-document link (the index page link is used instead).
- **Disclosure comparison limits** are listed in [DISCLOSURE_CHANGES.md](DISCLOSURE_CHANGES.md#5-limitations):
  paragraph-level matching, keyword topic tags, Risk Factors and MD&A only, and no
  human-labeled precision yet.
- **Review state is local.** Reviewed / needs-follow-up marks are stored in a SQLite file on
  the machine running the dashboard (`<data_dir>/reviews.sqlite`), for one analyst; there are
  no user accounts.
