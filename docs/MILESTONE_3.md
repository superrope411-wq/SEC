# Milestone 3 in plain language

PROJECT_SPEC.md, section 11: "Add three-company coverage, section comparison,
period-alignment warnings, and reviewed findings. Acceptance: demonstrate useful changes
while suppressing formatting noise."

## What was built

1. **Salesforce and Adobe**, loaded by the same pipeline as Microsoft and checked against
   their filings line by line: Salesforce FY2026 422/422 checks, Adobe FY2025 452/452.
2. **Disclosure comparison**: Risk Factors and MD&A of a filing against the same section of
   the right earlier filing, showing added, removed and reworded paragraphs with highlighted
   before/after text and links, and hiding formatting-only differences.
3. **Compare companies**: the three companies side by side, with a warning every time their
   periods do not cover the same days (which is always).
4. **Reviewed findings**: each financial or disclosure finding can be marked "reviewed" or
   "needs follow-up" with a note; the marks are saved and appear in the Excel exports.

## The decisions, and why

**Keeping Microsoft, Salesforce and Adobe even though their calendars don't match.**
Microsoft's fiscal year ends June 30, Salesforce's January 31, and Adobe's on the Friday
nearest November 30. So Microsoft's quarters end in Mar/Jun/Sep/Dec, Salesforce's one month
later (Jan/Apr/Jul/Oct) and Adobe's one month earlier (late Feb/May/Aug/Nov). Their quarters
*never* cover the same three months. Picking three December year-end companies would avoid
the problem, but analysts face it constantly, and handling it openly is more convincing
than avoiding it.

**How quarters are lined up (your choice on 2026-10-21).** You pick an anchor company and
period. Each other company contributes its quarter with the most days in common with the
anchor's, and the screen always shows the exact dates, how many days apart the quarters
end, which months they share, and how long each quarter is (Adobe's are 13 or 14 weeks).
Only each company's *own* changes are compared (growth versus its own prior year, margins),
because a growth rate is much less distorted by a one-month offset than a dollar total is.
Fiscal years overlap by only about seven months, and the screen says so.

**Never trusting a tag name.** XBRL concepts have official definitions, but companies use
them differently. Adobe labels its long-term (non-current) debt with `LongTermDebt`, whose
official definition *includes* short-term debt; Salesforce uses the same tag for its total
debt. The pipeline found this because the verification compares, for every line on the
balance sheet, the concept the company used with the concept the pipeline picked. The fix
is a short, documented list of company-specific concepts for Adobe only.

**Comparing only like with like.** A 10-K is compared with the previous 10-K, and a 10-Q
with the 10-Q for the same quarter a year earlier. A 10-Q is never compared with a 10-K: a
10-Q only has to report changes in risk factors, so a short 10-Q section does not mean a
risk disappeared. If a 10-Q just refers back to the annual report, the tool says so.

**Suppressing noise with rules you can read, not a model.** Text is normalized (quotes,
dashes, spacing, bullets, hyphenation), paragraphs split by page breaks are joined, and
paragraphs are matched wherever they moved. A paragraph that differs only in dates or
numbers is a "routine update"; one with three or fewer changed words is a "minor edit";
a list that was turned into one paragraph is a "split or merge". Everything else is added,
removed or changed, ranked by how much genuinely new or dropped language it has.

**Saying what a change is about without judging it.** Topic tags (legal/regulatory, AI,
cybersecurity, tax, deals and debt, and so on) come from keyword rules on the changed words
only, and show the words that triggered them. They do not say a change is good or bad.

## Results

| What | Result | Reproduce |
|---|---|---|
| Salesforce FY2026 vs its filings | 422/422 pass | `python evaluation/verification/reconcile.py CRM` |
| Adobe FY2025 vs its filings | 452/452 pass (408/452 before the debt fix) | `... reconcile.py ADBE` |
| Reference figures printed in the filings' documents | 466/466 | `check_documents.py CRM` / `ADBE` (needs SEC access) |
| Disclosure comparison, formatting noise only | 0 false changes in 1,503 real paragraphs | `python evaluation/m3/disclosure_noise_test.py` |
| Disclosure comparison, planted edits | 180/180 found, 0 extra | same |
| Real comparisons (12 sections) | 33 to 152 substantive changes each, under 1.5 s each | `python evaluation/m3/real_comparisons.py` |
| Precision on real changes (hand-labeled) | **not measured yet**: 40-item blinded sample ready | `evaluation/m3/label_sheet.csv`, then `score_labels.py` |

## What failed or is unfinished

- **Adobe debt** failed 44 checks until the company-specific concepts were added (above).
- **The first noise test reported 146 false changes.** The bug was in the test, not the
  tool: its simulated page breaks skipped the joining step that real filings go through.
- **The section splitter only knew Microsoft's layout.** Salesforce and Adobe put each
  paragraph in a `<div>`, not a `<p>`, so at first every paragraph of their filings landed
  in "cover page". Fixed; Microsoft's passages and evidence IDs are byte-for-byte unchanged,
  so the Milestone 2 evaluation still holds.
- **Precision on real changes is unmeasured** until the sample is labeled. The controlled
  test shows the rules work as designed; it cannot show the remaining changes are all
  useful. MD&A in particular is rewritten every year, so it has many "changed" paragraphs.
- Only one fiscal year per company is reconciled; financial-statement notes are not
  compared; review marks are local to one machine.

## Who did what

Ronin set the goals and rules (spec, wording rule, real data only, one milestone at a time)
and chose the closest-overlap alignment rule. Keeping the three companies was Claude's
recommendation in the plan; Ronin had not ruled on it when this was written. Claude
(AI) wrote the code, tests and documents in this milestone, chose the label specs used to
read the statements, and ran the verification. The noise test and the label sheet were
designed so that someone other than the code's author can check the results.
