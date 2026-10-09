# Independent review of evaluation/m2/questions.csv

- Reviewer: an independent Claude agent (Claude Code, model Opus 5.5), not a human.
- Date: 2026-10-09
- Scope: all 19 rows (S1-S8, A1-A4, U1-U7).

## Method

- I read the four saved filings (`tests/fixtures/real/filings/<accn>/*.htm.gz`) with my own script, kept outside the repo. It decompresses the file, removes script/style and the inline-XBRL header, strips tags, runs `html.unescape`, normalizes curly quotes and NBSP, and collapses whitespace. I imported, ran or read nothing from `src/` or `app/`.
- Check 1 (quotes): I searched for each gold quote as an exact substring of the normalized text. I counted how many times it occurs and found the nearest preceding Item heading and period heading ("Three/Six/Nine Months Ended ..." or "Fiscal Year 2025 Compared with Fiscal Year 2024").
- Check 3 (numbers): I recomputed each dollar and percent change from the filing's own income statement or cash flow statement (Item 1 / Item 8).
- Check 4 (unanswerable rows): I searched the whole filing with regexes for the absent fact. Terms included Azure near "$"; counts of customers, users or seats; "fourth quarter" and "three months ended June"; "fiscal year 2026", "expect" and "outlook"; capital expenditures, property and equipment, and datacenter; Adobe; stock price, share price and market price.
- All 21 gold quotes appear verbatim. Every one is in 10-K Part II Item 7 or 10-Q Part I Item 2. Every dollar and percent figure in them matches the statements, as rounded in the filing.

### Figures recomputed from the statements ($ millions)

| Item | Current | Prior | Change | % | Printed in quote |
|---|---|---|---|---|---|
| FY25 revenue | 281,724 | 245,122 | 36,602 | 14.93 | $36.6B / 15% |
| FY25 cost of revenue | 87,831 | 74,114 | 13,717 | 18.51 | $13.7B / 19% |
| FY25 operating expenses (R&D+S&M+G&A) | 65,365 | 61,575 | 3,790 | 6.16 | $3.8B / 6% |
| FY25 cash from operations | 136,162 | 118,548 | 17,614 | - | $17.6B to $136.2B |
| FY25 additions to property and equipment | 64,551 | 44,477 | 20,074 | 45.1 | $20.1B |
| FY25 Intelligent Cloud revenue (segment table) | 106,265 | 87,464 | 18,801 | 21.50 | $18.8B / 21% |
| FY25 Microsoft Cloud revenue (Item 8, Note 18) | 168.9B | 137.7B | - | 22.7 | 23% to $168.9B |
| FY25 gross margin % | 68.8% | 69.8% | -1.0 pt | - | "decreased slightly" |
| FY25 operating margin % | 45.6% | 44.6% | +1.0 pt | - | (no MD&A sentence) |
| Q1 FY25 revenue | 65,585 | 56,517 | 9,068 | 16.04 | $9.1B / 16% |
| Q2 FY25 revenue | 69,632 | 62,020 | 7,612 | 12.27 | $7.6B / 12% |
| Q2 FY25 operating income | 31,653 | 27,032 | 4,621 | 17.09 | $4.6B / 17% |
| H1 FY25 operating income | 62,205 | 53,927 | 8,278 | 15.35 | $8.3B / 15% (must_not) |
| H1 FY25 revenue | 135,217 | 118,537 | 16,680 | 14.07 | $16.7B / 14% (not in must_not) |
| Q3 FY25 revenue | 70,066 | 61,858 | 8,208 | 13.27 | $8.2B / 13% |
| Q3 FY25 operating income | 32,000 | 27,581 | 4,419 | 16.02 | $4.4B / 16% |
| 9M FY25 revenue | 205,283 | 180,395 | 24,888 | 13.80 | $24.9B / 14% |
| 9M FY25 operating income | 94,205 | 81,508 | 12,697 | 15.58 | $12.7B / 16% |
| Derived Q4 FY25 revenue (FY minus 9M) | 76,441 | Q3: 70,066 | 6,375 | 9.1 | (not printed) |

## Per-question verdicts

| id | Verdict | What I checked | Problems found (with filing text) |
|---|---|---|---|
| S1 | agree | Both quotes are verbatim, each once, in Item 7 under "Fiscal Year 2025 Compared with Fiscal Year 2024". $36.6B/15% = 281,724 - 245,122. | None. The next two sentences ("Productivity and Business Processes revenue increased driven by Microsoft 365 Commercial cloud. More Personal Computing revenue increased driven by Gaming and Search and news advertising.") are equally valid support and could be accepted as optional quotes. |
| S2 | agree with changes | Quote is verbatim, once, in Item 7 FY25-vs-FY24 summary. $3.8B/6% = 65,365 - 61,575 (6.16%). | The rationale says the figures are "unchecked". In the filing they are checkable against the income statement (R&D 32,488 + S&M 25,654 + G&A 7,223 = 65,365), so the claim describes the pipeline, not the filing. `must_not` is empty. The 10-K repeats similar wording at segment level, which an answer could cite by mistake: "Operating expenses increased $1.5 billion or 7% driven by investments in cloud and AI engineering." (Intelligent Cloud) and "Operating expenses increased $1.3 billion or 9% driven by Gaming, including the impact of the Activision Blizzard acquisition." (More Personal Computing). |
| S3 | agree | Quote is verbatim, once, in Item 7 Liquidity, "Cash Flows". 136,162 - 118,548 = 17,614, which rounds to $17.6B, ending at $136.2B. | None. |
| S4 | agree with changes | Revenue quote is verbatim, once, under "Three Months Ended March 31, 2025 Compared with Three Months Ended March 31, 2024". $8.2B/13% = 70,066 - 61,858. must_not ($24.9B/14%) matches the nine-month sentence. | The second gold quote, "Intelligent Cloud revenue increased driven by Azure.", occurs twice in this 10-Q: once in the three-month paragraph and once in the nine-month paragraph. A string-match grader cannot tell which one an answer cited, so a nine-month citation would score as correct. |
| S5 | agree | Quote is verbatim, once, in the three-month paragraph. $4.4B/16% = 32,000 - 27,581 (16.02%). | The nine-month operating income growth is also 16% ("Operating income increased $12.7 billion or 16% ..."), so must_not can only catch it by the $12.7B figure; it should say so. Optional extra context in the same paragraph: "Revenue, gross margin, and operating income included an unfavorable foreign currency impact of 2%, 2%, and 3%, respectively." |
| S6 | agree | Both quotes are verbatim, each once. The Q1 10-Q has only a three-month comparison. $9.1B/16% = 65,585 - 56,517. | None. |
| S7 | agree | Quote is verbatim, once, in the three-month paragraph. $4.6B/17% = 31,653 - 27,032. must_not ($8.3B/15%) matches 62,205 - 53,927. | None. |
| S8 | agree with changes | Quote is verbatim, once. $7.6B/12% = 69,632 - 62,020. "More Personal Computing revenue was relatively unchanged." is present (14,651 vs 14,641). | `must_not` names the wrong attribution but not the six-month sentence that carries it: "Revenue increased $16.7 billion or 14% driven by growth across each of our segments." (135,217 - 118,537 = 16,680). That six-month sentence is the most likely wrong citation and should be named explicitly. |
| A1 | agree | Both quotes are verbatim, each once, in the FY25 summary in Item 7. Gross margin % fell from 69.8% to 68.8%. Operating margin rose from 44.6% to 45.6%. | Ambiguity is real. Note that the 10-K gives no MD&A reason for the operating-margin change. The only nearby text is forward-looking: "The investments we are making in cloud and AI infrastructure and devices will continue to increase our operating costs and may decrease our operating margins." So the operating-margin reading can end only as inferred or insufficient evidence, which allowed_status permits. |
| A2 | agree with changes | All three quotes are verbatim, each once, all in Item 7. $168.9B is confirmed by Item 8 ("was $ 168.9 billion, $ 137.7 billion ... in fiscal years 2025, 2024"). Intelligent Cloud: 106,265 - 87,464 = 18,801 (21%). | The gold quote "Revenue increased $18.8 billion or 21%." is the Intelligent Cloud segment sentence, but on its own it reads like total revenue. This is exactly the error must_not warns against, so the row should label the quote as Intelligent Cloud segment. The Azure 34% figure cannot be checked against any statement, because no Azure dollar amounts exist. |
| A3 | agree with changes | Both quotes are verbatim, each once, under the three-month and nine-month headings. $8.2B/13% and $24.9B/14% both recompute. | The ambiguity is real for the figures, but both readings give the same headline reason ("with growth across each of our segments"). They differ only in the More Personal Computing driver ("driven by Search and news advertising" for the quarter vs "driven by Gaming and Search and news advertising" for nine months). The `comparison` column says `yoy` (quarter vs year-ago quarter), which fits only one of the two readings. `must_not` is empty; it should forbid presenting nine-month figures as the quarter or vice versa without labeling. |
| A4 | agree | Both quotes are verbatim, each once, in the FY25 summary. $13.7B/19% and $3.8B/6% recompute. | None. |
| U1 | agree with changes | Searched the whole 10-K for Azure near any dollar amount. No Azure dollar figure exists; only "Azure and other cloud services revenue grew 34%" and the 34% highlight. | `must_not` lists $18.6B and $106.3B but misses two other dollar figures that contain Azure and could be passed off as Azure revenue. One is "Server products and cloud services $ 98,435" (Item 8 product table). The other is "Microsoft Cloud revenue, which includes ... Azure and other cloud services ... was $ 168.9 billion". |
| U2 | agree with changes | Searched for "fourth quarter", "three months ended June" and quarterly tables. The 10-K has no Q4-vs-Q3 results discussion; Q4 mentions are only share repurchases, dividends, internal control and Rule 10b5-1. Derived Q4 revenue is 76,441 vs Q3 70,066 (+6,375). | The 10-K MD&A does contain a general management statement about fourth-quarter revenue: "Seasonality Our revenue fluctuates quarterly and is generally higher in the fourth quarter of our fiscal year. Fourth quarter revenue is driven by a higher volume of multi-year contracts executed during the period." It is general, not specific to FY25 Q4 vs Q3, but it is a real MD&A reason for Q4 being higher. As written, `must_not` ("a management statement about Q4 vs Q3") could penalize an answer that cites it correctly as a labeled inference, and `required_facts` does not mention it. |
| U3 | agree with changes | Searched for "fiscal year 2026", "expect", "outlook" and "guidance". No revenue forecast for FY2026 exists. | Forward-looking revenue-related numbers do exist and could be misused as a forecast. One is "We expect to recognize approximately 40 % of our total company remaining performance obligation revenue over the next 12 months" (RPO $375 billion, Item 8). The other is the unearned revenue recognition table "Three Months Ending September 30, 2025 $ 25,191 ... June 30, 2026 5,889" (Item 7). Neither is in `must_not`. The rationale ("Caught by the scope check before any model call") describes the pipeline and cannot be verified from the filing. |
| U4 | agree | The string "Adobe" does not appear anywhere in the Q3 10-Q. | The `comparison` value (`yoy`) has no meaning for this row, which is harmless. |
| U5 | agree | Searched for numbers adjacent to customers, users, organizations, developers, subscribers and seats. No Azure customer count exists. The only counts are cybersecurity counts (e.g. "We track over 1,500 unique threat actors") and employee headcount. | None. |
| U6 | disagree | The gold fragment is verbatim, once, in Item 7 "Cash Flows". 64,551 - 44,477 = 20,074, which rounds to $20.1B. | (1) The gold quote is a fragment, not a sentence. The sentence begins "Cash used in investing decreased $24.4 billion to $72.6 billion ..." and the capex increase appears only as an offset. (2) The rationale ("mentioned elsewhere only in general terms") understates what the MD&A says. Item 7, "Other Planned Uses of Capital": "We will continue to invest in capital expenditures to support growth in our cloud offerings and our investments in AI infrastructure and training." Item 7 overview: "We continue to identify and evaluate opportunities to expand our datacenter locations and increase our server capacity to meet the evolving needs of our customers, particularly given the growing demand for AI services." Item 8 Note 6: "we have committed $ 32.1 billion for the construction of new buildings ... primarily related to datacenters." These are management statements of what capital expenditures are for, in MD&A. They do not tie the $20.1B year-over-year increase to a cause in one sentence, so the best answer is a labeled inference citing them, not "insufficient evidence". Calling the row `unanswerable` and forbidding "a management statement giving a cause" risks penalizing the best-supported answer. |
| U7 | agree | No stock-price explanation anywhere in the Q3 10-Q. "trading price of our common stock" appears only as a risk-factor boilerplate phrase, and "a decline in our stock price" only as a goodwill-impairment trigger. | The question assumes the stock fell, which the filing does not establish. The repurchase table shows falling average prices paid ("$ 427.65", "408.03", "387.84" for January, February, March 2025), so an answer might treat these as stock-price evidence or infer a reason from them. Consider adding that to `must_not`. |

## Counts

- agree: 10 (S1, S3, S5, S6, S7, A1, A4, U4, U5, U7). S5 and U7 also carry optional suggestions (items 5 and 11 below).
- agree with changes: 8 (S2, S4, S8, A2, A3, U1, U2, U3)
- disagree: 1 (U6)

## Suggested changes

1. **U6 (disagree):**
   - Change category to `ambiguous`, or keep `unanswerable` but make `inferred` the expected status.
   - Replace the fragment gold quote with the full sentence ("Cash used in investing decreased $24.4 billion to $72.6 billion for fiscal year 2025, ... and a $20.1 billion increase in additions to property and equipment.").
   - Add as gold or acceptable quotes: "We will continue to invest in capital expenditures to support growth in our cloud offerings and our investments in AI infrastructure and training." and "We continue to identify and evaluate opportunities to expand our datacenter locations and increase our server capacity to meet the evolving needs of our customers, particularly given the growing demand for AI services."
   - Rewrite `must_not` to "presenting the cloud/AI capex purpose as an explicit stated cause of the $20.1 billion year-over-year increase without labeling it an inference", instead of banning any management statement.
   - Fix the rationale accordingly.
2. **U2:**
   - Add to `required_facts`: the 10-K MD&A "Seasonality" sentence ("Our revenue fluctuates quarterly and is generally higher in the fourth quarter of our fiscal year. Fourth quarter revenue is driven by a higher volume of multi-year contracts executed during the period.") may be cited only as a general, labeled inference.
   - Narrow `must_not` so it does not penalize that citation.
3. **S4:** Make the "Intelligent Cloud revenue increased driven by Azure." gold quote position-specific (the occurrence in the three-month paragraph), or drop it. It appears in both the three-month and nine-month paragraphs of the Q3 10-Q.
4. **S8:** Add the six-month sentence to `must_not`: "Revenue increased $16.7 billion or 14% driven by growth across each of our segments."
5. **S5:** In `must_not`, name the nine-month operating income sentence by its dollar figure ($12.7 billion), since its percent (16%) is identical to the quarter's.
6. **S2:**
   - Correct the rationale: the $3.8B/6% figure is checkable against the income statement (65,365 vs 61,575).
   - Add to `must_not` the segment-level operating expense figures ($1.5 billion or 7%, $1.3 billion or 9%, $1.1 billion or 4%) presented as the company total.
7. **A2:** Label the "Revenue increased $18.8 billion or 21%." gold quote as the Intelligent Cloud segment sentence (e.g. a note in rationale or required_facts). Read alone, it looks like company revenue.
8. **A3:**
   - Note in the rationale that both readings give the same headline reason and differ only in figures and the More Personal Computing driver.
   - Add `must_not`: nine-month figures presented as the quarter, or the reverse, without labeling.
   - The `yoy` comparison value fits only one reading.
9. **U1:** Add to `must_not` the $98,435 million (≈$98.4B) Server products and cloud services revenue and the $168.9B Microsoft Cloud revenue presented as Azure revenue.
10. **U3:**
    - Add to `must_not` the RPO ($375 billion, ~40% recognized in the next 12 months) and the unearned revenue recognition schedule presented as a FY2026 revenue forecast.
    - Mark the "scope check" rationale as a pipeline note, not a filing fact.
11. **U7 (optional):** Add to `must_not` any reason inferred from the Item 2 repurchase table's average prices paid ($427.65 / $408.03 / $387.84). Note that the filing does not establish the premise that the stock fell.
12. **S1 (optional):** Accept the Productivity and Business Processes and More Personal Computing driver sentences as additional valid quotes.

## Response from the author (applied to questions.csv)

Applied: 1 (U6 moved to a new category `inference_only`, expected `inferred`, with `insufficient evidence` also accepted as a cautious answer; full cash-flow sentence and the capital-spending sentence added as gold quotes; `must_not` narrowed), 2, 3 (the repeated Azure sentence was dropped from S4's gold quotes), 4, 5, 6, 7, 8 (`must_not` added), 9, 10, 11.

Not applied:
- 1, second quote: the datacenter-capacity sentence ("We continue to identify and evaluate opportunities to expand our datacenter locations...") is in Part I Item 1A (Risk Factors) of the 10-K, not Item 7, so it was not added as an MD&A gold quote.
- 12 (optional): S1 keeps its two gold quotes; citing the other segment-driver sentences is not penalized by the grader, which needs only one gold citation.
