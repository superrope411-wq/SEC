# Disclosure changes (Milestone 3)

What changed in the words of a filing, not just the numbers: the tool compares the same
section of two filings and shows what was added, removed or reworded, with before-and-after
excerpts and links, while hiding changes that are only formatting. No model is involved.

Code: `src/earnings_monitor/disclosure_diff/` (`compare.py` matching, `significance.py`
tags, `service.py` filing pairs). Dashboard: the **Disclosure changes** tab.

## 1. Which filings are compared

| Later filing | Compared with | Why |
|---|---|---|
| 10-K | the previous 10-K | Same disclosure requirements, one year apart. |
| 10-Q | the 10-Q for the same fiscal quarter a year earlier (default), or the previous 10-Q | Same quarter a year apart removes seasonal wording; the previous 10-Q is offered for "what changed since last quarter". |

A 10-Q is never compared with a 10-K. A 10-Q only has to report *material changes* to risk
factors (Form 10-Q, Part II, Item 1A), and many 10-Qs simply refer back to the annual
report. Comparing a short 10-Q section with a long 10-K section would wrongly report most
risks as "removed". If a 10-Q's section is a short reference ("no material changes",
"incorporated by reference", "refer to … our Annual Report"), the tool says so and does not
diff it. If a section cannot be found, it says that instead of reporting everything as
removed. (In the three 10-Qs used here, each company restates its full risk factors, so the
reference check has not been triggered on real data yet; it is covered by the rule above,
not by a real example.)

Sections: Risk Factors (10-K Part I Item 1A; 10-Q Part II Item 1A) and Management's
Discussion and Analysis (10-K Part II Item 7; 10-Q Part I Item 2). Financial-statement notes
are not compared yet.

## 2. How the comparison works

1. **Paragraphs.** The section's paragraphs and bullets are taken from the filing's main
   HTML document (the same passages, with the same evidence IDs, as the Milestone 2
   explanations). Table rows are left to the financial tables. A paragraph that a page break
   split in two (one piece ends mid-sentence, the next starts in lower case) is joined back.
2. **Normalization.** Case, curly quotes, dashes, bullet characters, non-breaking spaces,
   footnote markers and hyphenation ("vertically-integrated" = "vertically integrated").
3. **Matching**, in passes; anything matched is removed from the pool:

   | Pass | Rule | Reported as |
   |---|---|---|
   | a | identical after normalization, anywhere in the section | unchanged (a moved paragraph is counted as "reordered", not as a change) |
   | b | identical once dates, years, fiscal-period labels and numbers are masked | routine update (the changed numbers are listed) |
   | c | most similar remaining pair, word-sequence similarity ≥ 0.5 (≥ 0.3 if under the same heading) | changed, or minor edit if at most 3 words differ and no number changed |
   | d | leftover text that is ≥ 80% present elsewhere in the other filing's section (5-word runs) | split or merge (e.g. a bulleted list turned into one paragraph) |
   | e | anything still left | added (later filing only) or removed (earlier filing only) |

4. **Noise** = unchanged, routine update, minor edit, split or merge. These are counted and
   shown in one line, not listed. **Substantive** = added, removed, changed.
5. **Ranking.** Substantive changes are ordered by how much *new* or *dropped* language they
   contain: words not covered by any 5-word run of the other filing's section, so text that
   was only moved does not count. Topic tags add weight.

## 3. "Why it may matter": topic tags

Keyword rules over only the added or removed words (`significance.py`): legal or
regulatory, artificial intelligence, cybersecurity or privacy, economy/trade/geopolitics,
acquisitions/debt/capital, tax, outlook language, and "figures in the text changed". Each
tag lists the exact words that triggered it. Tags say what a change is *about*; they do not
say whether it is good or bad, and they are not a judgement of materiality. A change is not
claimed to be a guidance revision: comparable guidance is not in these sections, and earnings
releases (8-K) would be needed for that.

## 4. Results

### Controlled noise test (real text, known edits)

`python evaluation/m3/disclosure_noise_test.py` → [evaluation/m3/noise_test.md](../evaluation/m3/noise_test.md).
For each of the 12 real sections, the later filing is compared with a copy that has only
formatting noise (quotes, dashes, double spaces, bullets, 20% of paragraphs moved, 10% split
across a page break, every year shifted by one, numbers changed, every heading renamed), and
then with 15 known edits on top (5 paragraphs from another company inserted, 5 deleted, 5
extended by a new sentence).

| | Result |
|---|---|
| False substantive changes from noise alone | 0 in 1,503 paragraphs |
| Known edits found | 180 of 180 |
| Extra substantive changes when edits are present | 0 |

What this shows and does not show: the noise is the kind I designed, so this is a test of
the rules doing what they are meant to do, not proof that every real formatting difference
is caught. The first run reported 146 false changes; the cause was a bug in the test (its
page-break splits bypassed the joining step the real pipeline applies), not in the
comparison. The test now goes through the same joining function.

### The 12 real comparisons

`python evaluation/m3/real_comparisons.py` → [evaluation/m3/real_comparisons.md](../evaluation/m3/real_comparisons.md)
(counts, timings and the five largest changes of each). Each comparison takes under 1.5
seconds once the filings are cached. Examples of what surfaces at the top:

- Salesforce FY2026 10-K, MD&A: new paragraphs on the $4.0 billion 364-day credit agreement
  for the Informatica acquisition, and on the July 2025 US tax law ("One Big Beautiful Bill
  Act").
- Adobe FY2025 10-K, Risk Factors: a new paragraph on the EU Digital Services Act, and a
  rewritten paragraph on AI-specific regulation.
- Microsoft FY2025 10-K, MD&A: the paragraph explaining non-GAAP measures and the critical
  accounting estimate on business combinations are no longer present.
- Salesforce FY2026 10-K, Risk Factors: 262 → 215 paragraphs. Salesforce condensed several
  bulleted lists (e.g. acquisition risks); where the text survived in a merged paragraph it is
  reported as a split/merge, and where it did not, as removed.

Counts of substantive changes are high in MD&A (57 to 95 per comparison) because MD&A
explains each period's numbers in new words every year. The "≥ 40 words new or dropped"
column and the dashboard's minimum-words filter separate the large changes from the
small ones.

### Hand-labeled sample (pending)

Whether the substantive changes are *useful* needs a person's judgement.
`python evaluation/m3/make_label_sheet.py` draws a fixed-seed, blinded sample of 40 real
differences (25 the tool calls substantive, 15 it suppresses as noise) into
`evaluation/m3/label_sheet.csv`; the tool's verdicts are kept apart in `label_key.csv`.
After labeling, `python evaluation/m3/score_labels.py` reports precision, the share of
suppressed items that really are noise, and a population-weighted recall estimate. **No
labels have been entered yet, so no precision or recall is claimed.**

## 5. Limitations

- Paragraph-level only. A single changed sentence inside a long paragraph is shown with
  word highlighting, but the paragraph is the unit that is counted.
- A paragraph rewritten so heavily that it shares less than half its word sequence with the
  original (or less than 30% under the same heading) is reported as one removal plus one
  addition, not as a change.
- Topic tags are keyword matches: "act" matches any "Act", "models" matches non-AI models.
  They are hints for sorting, and each shows its trigger words so a false match is visible.
- Section detection depends on each company's "ITEM 1A." style headings. It works for the
  three companies' current filings; an unusual layout could make a section look missing,
  which the tool reports rather than treating as a removal.
- Only Risk Factors and MD&A. Notes to the financial statements are not compared.
