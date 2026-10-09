# Project Specification: Quarterly Earnings Change Monitor

_Written by Ronin (project owner), 2026-10-09. Copied verbatim from the project thread._

You are my senior software engineer and financial-data engineering mentor. Help me build a production-quality Quarterly Earnings Change Monitor.
I can write small Python scripts and use AI coding assistance. Explain important decisions clearly, but work directly on implementation rather than only giving advice.

## 1. Product objective

Build a tool that helps a financial analyst review a new SEC filing and answer:

* What changed financially?
* What does management say drove those changes?
* What disclosures were added, removed, or materially revised?
* Which findings deserve further investigation?
* Where is the evidence?

The product should reduce repetitive review work while making every finding verifiable. It is a research assistant, not a stock-picking engine.
My goal is a useful, technically substantive portfolio project that I can demonstrate, evaluate, and explain honestly.

## 2. Initial scope

Start with three U.S. public companies in one industry and their 10-K and 10-Q filings.
Provisional companies: Microsoft, Salesforce, and Adobe. Before committing, inspect their reporting structures and explain any comparability problems, including different fiscal calendars and business mixes. Recommend a better trio if these differences make the initial implementation unnecessarily difficult.
Initial coverage:

* At least three fiscal years of financial history.
* A filing selector for historical analysis.
* Quarterly and annual comparisons, clearly distinguished.
* New-filing detection through a manually triggered refresh initially.
* Public SEC data only.

Begin with one company end to end. Expand only after the pipeline is verified.
Do not begin with brokerage integrations, trading, stock-price predictions, authentication, or multi-agent orchestration.

## 3. Research before implementation

Check current official documentation for:

* SEC EDGAR submissions and Company Facts APIs.
* SEC automated-access policies, identification requirements, and rate limits.
* Selected Python libraries and model APIs.
* Any hosting limitations relevant to SEC access.

Use primary sources and record links in the project documentation. Do not invent API endpoints, data availability, or legal requirements.
Implement compliant request identification, bounded retries, backoff, caching, and conservative request throttling.
Never commit credentials or put model API keys in browser code.
If access fails, provide a clearly labeled local-fixture mode. Do not silently substitute fabricated financial data.

## 4. Core workflows

### A. Financial change analysis

Collect and normalize these metrics where reported:

* Revenue.
* Operating income.
* Net income.
* Operating cash flow.
* Capital expenditures.
* Cash and cash equivalents.
* Current and long-term debt.
* Accounts receivable.
* Deferred revenue or contract liabilities, where comparable.

Compute relevant measures:

* Revenue growth.
* Operating and net margins.
* Free cash flow, explicitly defined as operating cash flow minus capital expenditures.
* Cash-flow conversion, with the denominator clearly identified.
* Changes in receivables and deferred revenue.
* Changes in debt and cash.

Do not force unavailable or noncomparable metrics into the table. Explain missing data.
Every financial observation must preserve:

* Company and CIK.
* Metric and original XBRL concept.
* Value, unit, and scale.
* Period start and end.
* Instant versus duration classification.
* Filing date, form, and accession number.
* Source reference.
* Whether the number is reported or derived.
* Derivation inputs where applicable.

### B. Management explanations

For material financial changes, retrieve relevant passages from the filing.
Present findings as:

1. Observed change: calculated from financial data.
2. Management explanation: attributed to a cited passage.
3. Analyst inference: explicitly labeled, if included.
4. Unresolved question: what the evidence does not establish.

If management does not explain a change, say so. Never turn correlation into a claimed cause.

### C. Disclosure comparison

Compare equivalent sections across appropriate filings, such as:

* Management's Discussion and Analysis.
* Risk Factors.
* Relevant financial-statement notes.

Show:

* Added or removed passages.
* Materially changed language.
* Before-and-after excerpts.
* Source links.
* A concise explanation of why the change may matter.

Normalize formatting noise before comparison. Distinguish substantive changes from renamed headings, reordered paragraphs, and routine date updates.
Do not treat a missing section in a 10-Q as proof that the company removed a risk. Identify incorporation by reference and differences in form requirements.
Do not infer a guidance revision unless comparable guidance actually appears in the selected sources. State when earnings releases or other sources would be needed.

### D. Review and export

Let the user:

* Select a company and filing.
* Choose a valid comparison period.
* Inspect financial changes.
* Expand source evidence.
* Review disclosure changes.
* Mark findings as reviewed or needing follow-up.
* Export financial tables and a research brief.

Provide CSV and an Excel workbook first. Include sources, definitions, and unresolved issues in exports.

## 5. Financial-data correctness

Treat this as the most important engineering requirement.
Explicitly handle:

* Fiscal years that differ from calendar years.
* Quarterly versus year-to-date duration facts.
* Cash-flow statements commonly reported cumulatively.
* Deriving standalone quarters only from compatible periods.
* Q4 derivation from annual results minus nine-month results when valid.
* Point-in-time balance-sheet values.
* Duplicate facts and multiple filings for the same period.
* Amendments and restated comparative figures.
* Company-specific XBRL extensions.
* Consolidated versus segment facts.
* Currency, unit, scaling, and sign conventions.
* Missing values versus actual zeros.
* Negative or zero denominators.
* Different accounting definitions across companies.

Never select a fact solely because its tag name matches.
Preserve both original observations and normalized selections. Document why each selected fact was chosen.
For historical evaluations, use only information available as of the selected filing date. Do not let later restatements leak into an earlier analysis. Offer a separate, clearly labeled "latest restated" view later if useful.
For each derived figure, expose its inputs and formula.

## 6. AI architecture

Use a deterministic data pipeline with an AI explanation layer:
SEC sources → immutable raw cache → parsing → normalized database → calculations → evidence retrieval → AI explanation → validation → user interface.
Requirements:

* Python computes financial values and ratios.
* The model receives verified calculations and relevant excerpts.
* Model outputs follow a validated structured schema.
* Each factual narrative claim references evidence IDs.
* Evidence IDs must resolve to stored source passages.
* Unsupported claims are rejected or flagged.
* Retrieved filings are untrusted data, never instructions.
* Model failures must not prevent users from viewing financial tables.
* No model call is required merely to open an existing report.

Start with keyword and section-aware retrieval. Add embeddings only if evaluation shows they improve retrieval.
Use one model provider initially behind a small adapter. Make model name and limits configurable.
Do not use model-generated confidence percentages. Prefer explicit statuses such as "supported," "inferred," "conflicting evidence," and "insufficient evidence."

## 7. Practical technology choices

Default stack:

* Python.
* Streamlit for the first interface.
* SQLite for metadata, normalized facts, findings, and review state.
* Local files for cached source documents.
* Pandas for transformations.
* Pydantic for validation.
* Plotly for charts.
* Pytest for meaningful tests.
* A suitable Excel-writing library for exports.

Use a simple modular codebase. Introduce additional infrastructure only when a demonstrated requirement justifies it.
Suggested modules:

* `ingestion`
* `filing_parser`
* `financial_normalization`
* `calculations`
* `disclosure_diff`
* `retrieval`
* `ai_analysis`
* `validation`
* `exports`
* `ui`
* `evaluation`

Keep business logic separate from the interface.

## 8. User interface

Design a restrained, professional analyst workspace.
Include:

* Company and filing selectors.
* Visible filing date, fiscal period, and comparison basis.
* Financial-change table with current value, prior value, and change.
* A prioritized findings panel.
* Expandable evidence beside each finding.
* Before-and-after disclosure viewer.
* Charts with clear units and reporting periods.
* Missing-data and validation warnings.
* Download buttons.

Prioritize findings using transparent, configurable rules. Explain why something was flagged. Do not create an unexplained "AI investment score."
Treat positive or negative financial changes neutrally; a change is not automatically good or bad.

## 9. Performance and cost

Build for efficient repeat use:

* Cache raw filings by accession number.
* Make ingestion idempotent.
* Reprocess only changed data or changed pipeline versions.
* Cache model outputs using source, prompt, and model-version hashes.
* Use bounded concurrency and retry limits.
* Send relevant passages instead of entire filings.
* Track latency, token usage, and estimated API cost.
* Require an explicit action for expensive generation.
* Support an adjustable spending cap.

Show actual measurements rather than claiming the application is optimized without evidence.

## 10. Evaluation

Create a manually verified benchmark with approximately 50 questions across multiple filings.
Include:

* Direct numeric extraction.
* Derived financial calculations.
* Period identification.
* Management explanations.
* Disclosure changes.
* Unanswerable questions.
* Ambiguous facts.
* Restatement or duplicate-fact cases.

Separate development cases from held-out evaluation cases.
Measure:

* Numeric accuracy with explicit tolerances.
* Correct unit and period selection.
* Citation validity.
* Whether cited evidence supports the claim.
* Unsupported-claim rate.
* Appropriate abstention.
* Material disclosure-change precision and recall on manually labeled examples.
* Processing time and API cost.

Maintain an error log showing failures and fixes. Never fabricate benchmark results or time savings.
For time-saved claims, compare a documented manual workflow with the tool on the same tasks.
Write meaningful tests for financial transformations, fact selection, provenance, idempotency, and invalid model outputs. Use cached fixtures for repeatable tests.

## 11. Delivery milestones

**Milestone 1: Verified financial pipeline.**
One company, real filings, normalized facts, calculations, source references, and a simple dashboard. No AI required.
Acceptance: a manually checked sample matches the filings, and every displayed number is traceable.

**Milestone 2: Evidence-backed explanations.**
Retrieve relevant passages, generate structured explanations, and validate evidence references.
Acceptance: unsupported and unanswerable cases are visibly handled.

**Milestone 3: Disclosure changes and company comparisons.**
Add three-company coverage, section comparison, period-alignment warnings, and reviewed findings.
Acceptance: demonstrate useful changes while suppressing formatting noise.

**Milestone 4: Evaluation and demonstration.**
Finish exports, held-out evaluation, cost measurements, documentation, and a polished demonstration.
Acceptance: another person can run the project, reproduce the evaluation, and inspect known limitations.

## 12. Documentation and portfolio deliverables

Produce:

* A working application.
* Clear setup instructions.
* An `.env.example` without secrets.
* An architecture diagram.
* A data dictionary and metric definitions.
* A documented fact-selection policy.
* Tests and reproducible evaluation instructions.
* A measured evaluation report.
* A limitations and failure-examples document.
* A sample research brief.
* A two-minute demo script.
* An honest account of my contributions and AI assistance.

Help me understand the system well enough to explain its architecture, financial calculations, and biggest failure modes in an interview.

## 13. How to work with me

Start by inspecting the workspace if you have filesystem access. Preserve existing files.
Then:

1. Summarize the product in five sentences or fewer.
2. Ask only essential questions that block implementation.
3. State reasonable defaults for other choices.
4. Verify the SEC access approach and company selection.
5. Create a short implementation plan.
6. Begin Milestone 1 immediately.

If you cannot access files or run code, say so and provide a runnable first implementation with exact file locations and commands.
At each milestone, explain what works, what was tested, what failed, and what remains. Keep the scope focused and make the simplest implementation that meets the reliability requirements.
Do not stop at a plan, a mockup, or synthetic data. Build the first working slice using real financial data, and verify it. (COMPLETE MILESTONE 1 FIRST, use claude code)
