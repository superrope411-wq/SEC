"""Re-check the Microsoft FY2025 reference dataset against the filings themselves.

Independent of the pipeline: imports nothing from earnings_monitor and never reads
companyfacts. For every row of evaluation/msft_fy2025_reference.csv it
  1. opens the EDGAR statement page the row cites (R2/R4/R6), finds the line item and the
     period column, and compares the printed number;
  2. checks the number appears as printed in the filing's main 10-Q/10-K HTML document.

Usage: SEC_USER_AGENT="Name email@example.com" python evaluation/verify_reference.py
Downloads are cached under data/reference_pages/ (git-ignored). Exit code 0 only if all match.
"""

from __future__ import annotations

import csv
import html
import io
import os
import re
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "evaluation" / "msft_fy2025_reference.csv"
CACHE = ROOT / "data" / "reference_pages"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/789019"
PRIMARY = {  # accession -> main document, from the filing index on EDGAR
    "0000950170-23-054855": "msft-20230930.htm", "0000950170-24-008814": "msft-20231231.htm",
    "0000950170-24-048288": "msft-20240331.htm", "0000950170-24-118967": "msft-20240930.htm",
    "0000950170-25-010491": "msft-20241231.htm", "0000950170-25-061046": "msft-20250331.htm",
    "0000950170-25-100235": "msft-20250630.htm",
}
LABELS = {  # line-item labels as printed on Microsoft's statements
    "revenue": ["Total revenue", "Revenue"], "operating_income": ["Operating income"],
    "net_income": ["Net income"], "operating_cash_flow": ["Net cash from operations"],
    "capex": ["Additions to property and equipment"],
    "cash": ["Cash and cash equivalents", "Cash and cash equivalents, end of period"],
    "accounts_receivable": [],  # label includes the allowance amount; matched by prefix below
    "debt_current": ["Current portion of long-term debt"], "debt_noncurrent": ["Long-term debt"],
    "deferred_revenue_current": ["Short-term unearned revenue"],
    "deferred_revenue_noncurrent": ["Long-term unearned revenue"],
    "assets": ["Total assets"], "short_term_debt": ["Short-term debt"],
    "liabilities_and_equity": ["Total liabilities and stockholders’ equity", "Total liabilities and stockholders' equity"],
}


def fetch(url: str, ua: str) -> bytes:
    path = CACHE / url.split("/data/789019/")[1].replace("/", "_")
    if not path.exists():
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        time.sleep(0.25)  # stay well under SEC's 10 requests/second
    return path.read_bytes()


def number(cell) -> float | None:
    s = str(cell).replace("$", "").replace(",", "").strip()
    if s in ("", "nan"):
        return None
    return -float(s.strip("()")) if s.startswith("(") else float(s)


def header(d: date) -> str:
    return d.strftime("%b. %d, %Y").replace("May.", "May")


def from_statement(row: dict, page: bytes) -> float | None:
    t = pd.read_html(io.BytesIO(page))[0]
    if not isinstance(t.columns[0], tuple):  # balance sheets have one header row
        t.columns = [(c, c) for c in t.columns]
    end = date.fromisoformat(row["period_end"])
    if row["period_start"]:
        months = round((end - date.fromisoformat(row["period_start"])).days / 30.44)
        cols = [c for c in t.columns[1:] if c[1] == header(end) and c[0].startswith(f"{months} Months Ended")]
    else:
        cols = [c for c in t.columns[1:] if header(end) in c]
    labels = t[t.columns[0]].astype(str)
    if row["metric_id"] == "accounts_receivable":
        hits = t[labels.str.startswith("Accounts receivable, net")]
    else:
        hits = t[labels.isin(LABELS[row["metric_id"]])]
    if hits.empty or not cols:
        return None
    # A cash-flow page shows cash at the start and end of each period; the end is the last column.
    v = number(hits.iloc[0][cols[-1] if "end of period" in hits.iloc[0, 0] else cols[0]])
    if row["metric_id"] == "capex" and v is not None:
        v = abs(v)  # printed as an outflow in parentheses; stored as a positive amount
    if v is None and float(row["value_musd"]) == 0:
        v = 0.0  # a dash on the statement
    return v


def main() -> int:
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua or "@" not in ua:
        print("Set SEC_USER_AGENT to a name and email (SEC requires it).")
        return 2
    rows = list(csv.DictReader(REF.open()))
    texts = {}
    problems = 0
    for r in rows:
        expected = float(r["value_musd"])
        got = from_statement(r, fetch(r["source_url"], ua))
        if r["accn"] not in texts:
            raw = fetch(f"{ARCHIVE}/{r['accn'].replace('-', '')}/{PRIMARY[r['accn']]}", ua).decode("utf-8", "ignore")
            texts[r["accn"]] = html.unescape(re.sub(r"<[^>]+>", " ", raw)).replace("\xa0", " ")
        token = f"{int(expected):,}"
        in_document = expected == 0 or re.search(rf"(?<![\d,]){re.escape(token)}(?![\d,])", texts[r["accn"]]) is not None
        if got != expected or not in_document:
            problems += 1
            print(f"PROBLEM {r['accn']} {r['metric_id']} {r['period_start']}..{r['period_end']}: "
                  f"reference {expected:,.0f}, statement page {got}, in main document: {in_document}")
    print(f"{len(rows)} reference values checked: {len(rows) - problems} match the statement page and "
          f"appear in the filing's main document; {problems} problems.")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
