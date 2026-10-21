"""Read the face financial statements of a filing from EDGAR's rendered statement pages.

Independent of the pipeline: imports nothing from earnings_monitor and never reads the
companyfacts API. For a filing it reads FilingSummary.xml to find the balance sheet, income
statement and cash-flow statement pages (R2.htm, R4.htm, ...), then parses each page into
rows of (printed label, XBRL concept on that line, value per column). Values are as printed,
in the statement's scale (millions for all three companies), with parentheses as negatives.

Pages are cached under data/reference_pages/ (git-ignored) and fetched at most 4/second.
"""

from __future__ import annotations

import os
import re
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import lxml.etree
import lxml.html

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "reference_pages"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data"

STATEMENT_KINDS = {  # matched against FilingSummary ShortName, lower case
    "balance": re.compile(r"^(condensed )?consolidated balance sheets?$"),
    "income": re.compile(r"^(condensed )?consolidated statements? of (operations|income)( \(unaudited\))?$"),
    "cashflow": re.compile(r"^(condensed )?consolidated statements? of cash flows?( \(unaudited\))?$"),
}


def user_agent() -> str:
    ua = os.environ.get("SEC_USER_AGENT", "")
    if "@" not in ua:
        raise SystemExit("Set SEC_USER_AGENT to a name and email (SEC requires it).")
    return ua


_last = [0.0]


def fetch(url: str) -> bytes:
    path = CACHE / url.split("/edgar/data/")[1].replace("/", "_")
    if not path.exists():
        wait = 0.25 - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
        _last[0] = time.monotonic()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    return path.read_bytes()


def folder(cik: int, accn: str) -> str:
    return f"{ARCHIVE}/{cik}/{accn.replace('-', '')}"


def statement_pages(cik: int, accn: str) -> dict[str, str]:
    """kind -> URL of the statement page, from the filing's FilingSummary.xml."""
    xml = lxml.etree.fromstring(fetch(f"{folder(cik, accn)}/FilingSummary.xml"))
    out: dict[str, str] = {}
    for rep in xml.iter("Report"):
        if (rep.findtext("MenuCategory") or "") != "Statements":
            continue
        name = re.sub(r"\s+", " ", (rep.findtext("ShortName") or "").strip().lower())
        for kind, pat in STATEMENT_KINDS.items():
            if kind not in out and pat.match(name):
                out[kind] = f"{folder(cik, accn)}/{rep.findtext('HtmlFileName')}"
    missing = set(STATEMENT_KINDS) - set(out)
    if missing:
        raise RuntimeError(f"{accn}: statement pages not found for {sorted(missing)}")
    return out


@dataclass
class Row:
    label: str
    concept: str  # e.g. "us-gaap:DebtCurrent"
    values: dict[tuple[int, date], float | None] = field(default_factory=dict)  # (months, end) -> value; months 0 = instant


@dataclass
class Statement:
    kind: str
    url: str
    title: str
    columns: list[tuple[int, date]]
    rows: list[Row]

    def find(self, label: str | re.Pattern, occurrence: int = 1) -> Row | None:
        n = 0
        for r in self.rows:
            ok = label.match(r.label) if isinstance(label, re.Pattern) else r.label == label
            if ok:
                n += 1
                if n == occurrence:
                    return r
        return None


_MONTHS = re.compile(r"(\d+) Months? Ended", re.I)


def _date(text: str) -> date | None:
    t = text.strip().replace("Sept.", "Sep.").replace("June", "Jun.").replace("July", "Jul.")
    for fmt in ("%b. %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


def _number(text: str) -> float | None:
    t = text.replace("$", "").replace(",", "").replace("\xa0", "").strip()
    if t in ("", "—", "-"):
        return None
    neg = t.startswith("(")
    t = t.strip("()").strip()
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def parse_statement(kind: str, url: str) -> Statement:
    doc = lxml.html.fromstring(fetch(url))
    table = doc.find(".//table[@class='report']")
    trs = table.findall("tr")
    # Header rows hold <th>. Row 1: title, then "N Months Ended" spans (or dates for a balance sheet).
    # Row 2 (if present): one date per column.
    head = [tr for tr in trs if tr.find("th") is not None]
    title = head[0].findall("th")[0].text_content().strip()
    spans: list[int] = []
    for th in head[0].findall("th")[1:]:
        m = _MONTHS.search(th.text_content())
        span = int(th.get("colspan") or 1)
        if m:
            spans += [int(m.group(1))] * span
        elif _date(th.text_content()):
            spans.append(0)
        else:
            spans += [-1] * span  # a blank/other header (e.g. a footnote column)
    if len(head) > 1:
        dates = [_date(th.text_content()) for th in head[1].findall("th")]
    else:
        dates = [_date(th.text_content()) for th in head[0].findall("th")[1:]]
    columns = [(m, d) for m, d in zip(spans, dates) if m >= 0 and d is not None]
    rows: list[Row] = []
    for tr in trs:
        tds = tr.findall("td")
        if not tds or "pl" not in (tds[0].get("class") or ""):
            continue
        a = tds[0].find(".//a")
        m = re.search(r"defref_([A-Za-z0-9-]+)_([A-Za-z0-9]+)", a.get("onclick") or "") if a is not None else None
        concept = f"{m.group(1)}:{m.group(2)}" if m else ""
        cells = [td for td in tds[1:] if "nump" in (td.get("class") or "") or "num" in (td.get("class") or "")
                 or (td.get("class") or "") in ("text", "")]
        values = {}
        for col, td in zip(columns, cells):
            values[col] = _number(td.text_content())
        rows.append(Row(re.sub(r"\s+", " ", tds[0].text_content()).strip(), concept, values))
    return Statement(kind, url, title, columns, rows)


def statements(cik: int, accn: str) -> dict[str, Statement]:
    return {k: parse_statement(k, u) for k, u in statement_pages(cik, accn).items()}
