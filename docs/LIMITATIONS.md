# Limitations and known failure modes (milestone 1)

- **Real-data verification is pending.** The cloud environment used to build this
  milestone could not reach `data.sec.gov` (network policy), so the pipeline has been
  validated only on synthetic fixtures with known answers. The golden-set comparison in
  `evaluation/` must be run on real Microsoft filings before milestone 1 is accepted.
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
  always shown so this can be checked.
- **Restatement detection is value-based.** A fact that was corrected in a later filing is
  flagged; a correction that only appears in an amendment's text (not XBRL) is not seen.
- **Fiscal calendar detection needs 10-K data.** A company with fewer than one full fiscal
  year of XBRL filings will not get a calendar.
- **Submissions "recent" list** can omit very old filings; those are added from facts but
  without a primary-document link (the index page link is used instead).
- **No text yet.** Management explanations and disclosure diffs are later milestones.
