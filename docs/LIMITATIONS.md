# Limitations and known failure modes (milestone 1)

- **Verified on one company and one fiscal year.** Microsoft FY2025 reconciles 200/200
  against figures read from the filings ([REAL_DATA_VERIFICATION.md](REAL_DATA_VERIFICATION.md)).
  Salesforce and Adobe are not yet verified.
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
- **No text yet.** Management explanations and disclosure diffs are later milestones.
