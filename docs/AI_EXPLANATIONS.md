# Milestone 2: evidence-backed explanations (Microsoft FY2025)

The financial pipeline from Milestone 1 is unchanged and still produces every number. This
milestone adds one thing on top: an answer to "why did this change?", built only from
passages of the filing, with each statement checked in code before it is shown.

## Pipeline

```
SEC filing HTML (10-Q / 10-K main document, cached unchanged)
  -> passages with evidence IDs, section, headings, page, period context, table cells   evidence/extract.py
  -> keyword + section + period retrieval                                              evidence/retrieve.py
  -> scope check (other company, future period): "insufficient evidence", no model     explain/service.py
  -> response cache (hash of prompt version, model, settings, full input)              explain/store.py
  -> model call, only on request, within a spending cap                                explain/llm.py
  -> validation: citations, quotes, numbers by metric/period/unit/value, status       explain/validate.py, figures.py
  -> dashboard Explanations tab                                                        app/explain_panel.py
```

A model failure (no key, rate limit, refusal, truncated output, malformed output, spending
cap) produces an explanation with the error written on it. It never raises into the
dashboard, and no model call is needed to open a report, see the tables or see the evidence.

## Evidence IDs and source links

Each paragraph, bullet and table row of the filing's main document becomes a passage. Its ID
is `<accession>:<section>:<10 hex>`, for example `0000950170-25-100235:PII-I7:e21d80cc7e`
(10-K, Part II Item 7, the sentence "Revenue increased $36.6 billion or 15% ..."). The hex is a
hash of the accession, section, passage kind and normalized text, so:

- the same filing always gives the same IDs (pinned in `tests/test_evidence.py`);
- an ID from one filing can never resolve in another;
- IDs do not shift when the extractor changes how it walks the document, only if the text it
  extracts changes.

Each passage carries the page number printed in the filing, the headings above it, the
segment name when the paragraph sits under one ("Intelligent Cloud"), the periods it talks
about (from headings like "Three Months Ended March 31, 2025 Compared with ..." or the
sentence itself), and for table rows each cell's column, period, unit and scale (from
"(In millions, except percentages)"). The source link is the EDGAR document URL with a
text fragment (`#:~:text=...`), which opens the filing scrolled to the passage in browsers
that support text fragments; the page number is shown alongside in case it does not.

The four FY2025 documents are saved unmodified (gzip) in `tests/fixtures/real/filings/` with
SHA-256 hashes in `manifest.json`. In live mode the app downloads them once from
`www.sec.gov/Archives` and caches them under `data/raw/filings/`.

## What the model gets and must return

Input: the calculated changes table (verified numbers from the pipeline) and the top 15
passages, each wrapped in a `<passage>` element with its attributes. The system prompt says the
passages are untrusted data and that instructions inside them must be ignored; a closing tag
inside passage text is neutralized so a passage cannot end its own element.

Output: a strict JSON schema (`explain/schema.py`, `ModelAnswer`):

- `management_statements`: what the filing says, each with citations `{evidence_id, quote}`;
- `inferences`: conclusions the filing does not state, each with `based_on` (evidence IDs
  or `calc:<metric>`) and `reasoning`;
- `figures`: every number taken from a passage, tied to a metric, a measure
  (current value, prior value, change amount, change percent) and the passage;
- `status`, `interpretation`, `ambiguity`, `insufficient_evidence_reason`, `unresolved_questions`.

The model never supplies the calculated numbers; the dashboard shows those from the pipeline.
No confidence percentages are produced or shown.

Model: `claude-opus-5-5` with adaptive thinking and effort `medium`, `max_tokens` 16,000,
through the official `anthropic` SDK (`messages.create` with `output_config.format`
json_schema). All of these are settings (`EM_AI_*`, see `.env.example`).

## Checks (in code, deterministic)

Management statement, accepted only if all pass:
1. at least one citation, and every evidence ID resolves to a passage of the analyzed filing;
2. every quote appears word for word in its passage (whitespace and quote marks normalized);
3. every number in the statement appears in a quote or is a verified figure;
4. at least 60% of the statement's content words appear in the quotes (lexical support);
5. a causal claim ("driven by", "due to", "because") needs causal wording in the quotes, and
   every content word of the stated cause must appear in the quotes;
6. no number in it failed the figure check.

Figure (a number from the filing), checked against the verified calculation:
- **metric**: a table row must be the metric itself ("Revenue", or "Total" under "Revenue");
  a sentence must have the metric as its subject. "Microsoft Cloud revenue increased 23% to
  $168.9 billion", "Intelligent Cloud: Revenue increased $18.8 billion or 21%" and the
  "Intelligent Cloud - Revenue" table row are all rejected as company revenue;
- **period**: the passage's period context must be the analyzed period (and prior period). In
  the Q3 10-Q the nine-month sentence "Revenue increased $24.9 billion or 14%" and the
  nine-month table columns are rejected for the quarter;
- **unit**: dollars for amounts and percent for percent changes, with scale applied
  ("$36.6 billion"; "281,724" under "(In millions)");
- **value**: equal to the pipeline's number within the printed precision ($36.6 billion vs
  $36,602 million passes; 15% vs 14.93% passes), with the direction ("increased"/"decreased")
  matching the sign. A number that passes metric, period and unit but disagrees in value is a
  **conflict**, not a rejection.

Inference, accepted only if it says what it is based on, every evidence ID resolves, every
`calc:` metric exists, and any number in it comes from the cited passages or the cited
calculations.

Status: `supported` (a management statement passed), `inferred` (only inferences passed),
`conflicting evidence` (a figure conflicts with the verified data), `insufficient evidence`
(nothing passed). The final status is the more cautious of this and the model's own status.
Rejected statements are kept and shown separately with their reasons.

"Insufficient evidence" is returned without any model call when the question names another
company, asks about a period after the filing (e.g. fiscal 2026), or retrieval finds nothing
(best score below 6.0).

## Cache, cost and the spending cap

`data/ai_cache.sqlite` (separate from the financial database) holds:
- `responses`: one validated answer per cache key. The key hashes the prompt version (which
  includes a hash of the system prompt), model, effort, max_tokens and the full input
  (passages, calculations, question). Validation is re-run on every read, so a change to the
  checks applies to cached answers too.
- `calls`: every API call, including failed ones, with input/output/cache tokens, cost and
  latency. `cache_hits` counts reuses (no cost).

Cost = tokens x price; Opus 5.5 is $4 per million input tokens and $20 per million output
tokens (thinking tokens are billed as output). Before a call the app adds the worst case for
that call (prompt length / 3 tokens per character x input price + max_tokens x output price,
about $0.34 for the example) to the recorded spend and refuses if that exceeds
`EM_AI_BUDGET_USD` (default $5.00). The dashboard shows the worst case before the button and a
running total below the panel.

## Evaluation set

`evaluation/m2/questions.csv`: 19 questions on the four FY2025 filings, split dev (10) and
held-out (9):

| category | count | what a correct answer does |
|---|---|---|
| supported | 8 | cites the gold MD&A sentence; status `supported` |
| ambiguous | 4 | names the ambiguity (e.g. "margins": gross, operating or Microsoft Cloud) |
| unanswerable | 6 | `insufficient evidence`, no accepted management statement (e.g. Azure revenue in dollars, Q4 vs Q3 in the 10-K, fiscal 2026, Adobe, customer counts, stock price) |
| inference_only | 1 | capital expenditures: the filing states the $20.1B increase and what capital spending is for, but not why it rose; answer `inferred` (or `insufficient evidence`) |

Each row has gold quotes (exact filing text), required facts, things the answer must not say
and a rationale. **Independent review**: a separate Claude agent, which was not allowed to use
the app's code, checked every row against the filing text and recomputed every figure from the
financial statements ([evaluation/m2/review.md](../evaluation/m2/review.md)). It agreed with 10
rows, suggested changes to 8 and disagreed with 1 (the capex question, which was
"unanswerable"; it is now `inference_only`). 11 of its 12 suggestions were applied; the reasons
for the others are at the end of the review. This is not a human review; Ronin should review
the set before it is treated as final.

Scoring (`evaluation/run_m2_eval.py`): offline it measures the scope check, whether every
gold quote is among the passages offered to the model, and whether each dollar and percent
change in the gold quotes passes the figure check. With `--live` it adds, per question, the
final status, whether it is allowed, whether an accepted statement cites a gold quote,
citation validity, rejected statements, tokens, cost and latency.

## Measured results

Offline, all 19 questions (`evaluation/m2/results_offline_all.md`, reproducible without a key):

| measure | result |
|---|---|
| questions stopped by the scope check, no model call | 2 / 2 that should be (U3 fiscal 2026, U4 Adobe); 0 false stops |
| gold quotes among the passages offered to the model | 16 / 21 |
| gold-quote figures passing the metric/period/unit/value check | 16 / 16 |
| offline pass (gold quotes all offered, or correctly stopped) | 12 / 15 scorable |
| time to extract and index one filing | about 0.5 s; retrieval about 0.03 s |

Failures: the 5 gold quotes not offered are all on ambiguous questions: A2 "How did the cloud
business do?" (the Microsoft Cloud bullet and the Intelligent Cloud segment sentence), A3 "Why
did revenue grow this year?" in the Q3 10-Q (the nine-month sentence is down-weighted because the
comparison is the quarter), and A4 "What happened to expenses?" (both gold sentences lose to
short "Other income (expense)" table rows). For these the model sees only one reading of the
question, so it cannot describe the others from evidence.

Retrieval was adjusted once after looking at these offline results, including held-out
questions (A4 is held-out): the second ranking with the raw question, the narrative-sentence
weight and k from 12 to 15. (A later bug fix, giving bullets the period of the sentence that
introduces them, moved A2 from 1/3 to 0/3 gold quotes offered; it was not tuned further.) The
held-out retrieval numbers are therefore not a clean held-out
measurement. Nothing else was tuned on the held-out split, and no model run has happened.

**Live model results: not yet measured.** This environment has no `ANTHROPIC_API_KEY`, so no
model output exists for any question and none is shown or simulated. When a key is available:

```bash
EM_MODE=fixture EM_FIXTURE_DIR=tests/fixtures/real python evaluation/m2_example.py --live
EM_MODE=fixture EM_FIXTURE_DIR=tests/fixtures/real python evaluation/run_m2_eval.py --live --split dev
EM_MODE=fixture EM_FIXTURE_DIR=tests/fixtures/real python evaluation/run_m2_eval.py --live --split heldout
```

The worst case is about $0.34 per question, $6.50 for all 19; expected cost is lower (most of
the worst case is the output limit). Raise `EM_AI_BUDGET_USD` above the $5.00 default to run
all questions in one go.

The end-to-end example up to the model call is in
[evaluation/m2/example_revenue_fy2025.md](../evaluation/m2/example_revenue_fy2025.md).

## Limitations

- Lexical support (rule 4) is a proxy for "the quote supports the claim", not proof. A
  statement that reuses the quote's words with a changed meaning (for example a negation) can
  pass. The figure checks and the causal-word rule narrow this but do not close it.
- The metric vocabulary (`evidence/vocab.py`) and the heading patterns are written for
  Microsoft's filing style. Salesforce and Adobe have not been tried.
- Period context comes from headings and phrases ("Fiscal Year 2025 Compared with ...",
  "Three Months Ended ..."); a passage without either has no period and cannot verify a
  figure.
- The 10-K does not discuss the fourth quarter on its own, so sequential (Q4 vs Q3) and
  Q4 year-over-year questions on the 10-K usually end in "insufficient evidence".
- Only the main 10-Q/10-K document is indexed. Exhibits (e.g. the earnings press release) are not.
- Text-fragment links can land on an earlier identical phrase (common for table rows such as
  "Revenue"); the page number is the reliable locator.
- The scope check is keyword-based: it catches named companies in the configured list and
  explicit future years, not every out-of-scope question; the model and the checks are the
  second line.
