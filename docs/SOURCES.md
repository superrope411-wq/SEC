# Sources

Primary sources checked on 2026-10-09. Nothing in this project relies on undocumented
endpoints.

## SEC EDGAR

- **EDGAR APIs** (endpoints, no authentication, no CORS, bulk ZIPs, update timing):
  https://www.sec.gov/search-filings/edgar-application-programming-interfaces
  - Submissions: `https://data.sec.gov/submissions/CIK##########.json`
  - Company Facts: `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`
  - Company Concept: `https://data.sec.gov/api/xbrl/companyconcept/CIK##########/us-gaap/<Concept>.json`
  - Frames: `https://data.sec.gov/api/xbrl/frames/us-gaap/<Concept>/USD/CY2019Q1I.json`
  - "These APIs do not require any authentication or API keys to access."
  - "data.sec.gov does not support Cross Origin Resource Scripting (CORS)." (So the browser
    must never call SEC directly; the Python backend does.)
  - XBRL APIs have "a typical processing delay of under a minute" after a filing.
- **Accessing EDGAR data / automated access**:
  https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
  - "Please declare your user agent in request headers." Sample:
    `User-Agent: Sample Company Name AdminContact@<sample company domain>.com`
  - "Current max request rate: 10 requests/second."
  - "SEC reserves the right to limit request rates to preserve fair access for all users."
  - Filing archive paths: `/Archives/edgar/data/{CIK}/{accession-no-dashes}/` and
    `/Archives/edgar/data/{CIK}/{accession}-index.html`.
- **Developer resources / fair access**: https://www.sec.gov/about/developer-resources
  - "Current guidelines limit each user to a total of no more than 10 requests per second."

How the code complies: `SEC_USER_AGENT` (name + email) is required for live mode and sent
on every request; the default ceiling is 4 requests/second (configurable, capped at 10);
retries are bounded (4 attempts) with exponential backoff and `Retry-After` honoured;
403 responses are never retried; raw responses are cached so a normal run makes at most
two requests per company.

## Hosting note

SEC data must be fetched server-side (no CORS, and the User-Agent must identify the
operator). Any hosted deployment therefore needs outbound access to `data.sec.gov` and
`www.sec.gov` from the Python process. If that is blocked, fixture mode reads saved
responses from disk and labels every screen and export as fixture data.

## Libraries

- requests, pandas, pydantic, openpyxl, streamlit, plotly, pytest, python-dotenv (see
  `pyproject.toml` for version floors).
