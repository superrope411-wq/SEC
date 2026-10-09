# Architecture (milestone 1)

```
SEC EDGAR (data.sec.gov)
   │  submissions API, companyfacts API         ingestion/sec_client.py
   │  User-Agent, ≤4 req/s, bounded retries
   ▼
Immutable raw cache  data/raw/<kind>/CIK…/<ts>_<sha>.json + manifest.jsonl
   │                                            ingestion/raw_cache.py, ingestion/ingest.py
   ▼
Parse → observations (every fact, unchanged)    financial_normalization/observations.py
   │   idempotent per (sha256, pipeline version)
   ▼
SQLite  observations · filings · companies · pipeline_runs    storage/db.py
   │
   ▼
Fiscal calendar from reported period dates      financial_normalization/calendar.py
   │
   ▼
Fact selection as of the filing date            financial_normalization/selection.py
   │   approved concepts, exact periods, YTD → quarter, Q4 = FY − 9M, restatement flags
   ▼
Calculations with provenance                    calculations/measures.py, calculations/flags.py
   │   FCF, margins, conversion, QoQ / YoY / annual changes, rule-based findings
   ▼
Validation                                      validation/checks.py
   │   balance-sheet identity, YTD consistency, missing / restated / sign checks
   ▼
Analysis object ──► Streamlit dashboard (app/dashboard.py)
                ──► CSV / Excel exports (exports/tables.py)
                ──► CLI (cli.py)
```

Design rules:

- **Python computes every number.** No model is involved in milestone 1, and when AI is
  added it will only receive values that already carry sources.
- **Original data is never modified.** Raw responses are stored by content hash; every
  fact is kept as an observation; normalized values point back to observation ids.
- **As-of semantics.** An analysis of a filing only uses facts filed on or before that
  filing's date. Choosing an older filing in the selector reproduces what was knowable then.
- **Interface is thin.** `app/dashboard.py` only renders `Analysis` objects; the same
  objects feed the CLI and exports, and tests exercise them without Streamlit.
- **Fixture mode is explicit.** When SEC is unreachable, `EM_MODE=fixture` reads saved
  responses and every screen and export is labeled; nothing is synthesized.
