"""Split a filing's main HTML document into citable passages.

Each passage is a paragraph, a bullet, or one row of a table, tagged with where it sits
(Part/Item, the headings above it, the page), what period it talks about, and, for table
rows, each cell's column, period, unit and scale. Those tags are what lets the validator
check a cited number by metric, period, unit and context rather than by string match.

Evidence IDs are "<accession>:<section>:<10 hex>", where the hex is a hash of the accession,
section, kind and normalized text (plus an occurrence count for repeated text). They do not
depend on the passage's position, so re-running the extractor on the same filing gives the
same IDs, and an ID from one filing can never resolve in another.
"""

from __future__ import annotations

import calendar
import hashlib
import re
from collections import Counter
from datetime import date
from typing import Literal
from urllib.parse import quote

import lxml.html
from pydantic import BaseModel, Field

MONTHS = {m: i for i, m in enumerate(calendar.month_name) if m}
_WORDS = {"three": 3, "six": 6, "nine": 9, "twelve": 12}
_ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4}


class Cell(BaseModel):
    column: str
    text: str
    value: float | None = None  # as printed, before scale (e.g. 281724 for "$281,724" in millions)
    unit: Literal["USD", "percent", "percentage_points", "number", "USD/share", ""] = ""
    scale: float = 1.0  # multiply value by this to get whole units
    period: str | None = None  # "<months>M:<end date>", e.g. "3M:2025-03-31"


class Passage(BaseModel):
    evidence_id: str
    accn: str
    form: str
    section: str  # e.g. "PII-I7"
    section_title: str
    headings: list[str] = Field(default_factory=list)  # nearest headings, outermost first
    subject: str | None = None  # e.g. a segment name printed above a short paragraph
    kind: Literal["paragraph", "list_item", "table_row"]
    text: str
    page: str | None = None
    periods: list[str] = Field(default_factory=list)  # period context, current first
    table_title: str | None = None
    table_note: str | None = None
    row_label: str | None = None
    row_group: str | None = None
    cells: list[Cell] = Field(default_factory=list)
    url: str = ""

    @property
    def is_mdna(self) -> bool:
        return self.section == ("PII-I7" if self.form.startswith("10-K") else "PI-I2")


def norm(s: str) -> str:
    s = s.replace(" ", " ").replace("’", "'").replace("‘", "'")
    s = s.replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).strip()


def _month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def period_key(months: int, end: date) -> str:
    return f"{months}M:{end.isoformat()}"


def fiscal_year_end(fy: int, fye: tuple[int, int]) -> date:
    return date(fy, fye[0], fye[1]) if fye[0] != 2 else _month_end(fy, 2)


def fiscal_quarter_end(fy: int, q: int, fye: tuple[int, int]) -> date:
    m = fye[0] - 3 * (4 - q)
    y = fy
    while m <= 0:
        m += 12
        y -= 1
    return _month_end(y, m)


_RANGE = re.compile(r"\b(three|six|nine|twelve) months ended ?([A-Z][a-z]+) (\d{1,2}),? ?(\d{4})?", re.I)
_FY = re.compile(r"\bfiscal (?:year )?(\d{4})\b|\bfiscal years? (\d{4})(?: and (\d{4}))?", re.I)
_QTR = re.compile(r"\b(first|second|third|fourth) quarter of fiscal (?:year )?(\d{4})", re.I)
_YEAR_ENDED = re.compile(r"\byears? ended ?([A-Z][a-z]+) (\d{1,2}),? ?(\d{4})?", re.I)


def find_periods(text: str, fye: tuple[int, int]) -> list[str]:
    """Period keys mentioned in a heading or sentence, in order of appearance."""
    found: list[tuple[int, str]] = []
    for m in _RANGE.finditer(text):
        if m.group(4) and m.group(2).capitalize() in MONTHS:
            end = date(int(m.group(4)), MONTHS[m.group(2).capitalize()], int(m.group(3)))
            found.append((m.start(), period_key(_WORDS[m.group(1).lower()], end)))
    for m in _QTR.finditer(text):
        end = fiscal_quarter_end(int(m.group(2)), _ORD[m.group(1).lower()], fye)
        found.append((m.start(), period_key(3, end)))
    for m in _FY.finditer(text):
        if text[max(0, m.start() - 15):m.start()].lower().endswith("quarter of "):
            continue
        for g in (1, 2, 3):
            if m.group(g):
                found.append((m.start(g), period_key(12, fiscal_year_end(int(m.group(g)), fye))))
    for m in _YEAR_ENDED.finditer(text):
        if m.group(3) and m.group(1).capitalize() in MONTHS:
            end = date(int(m.group(3)), MONTHS[m.group(1).capitalize()], int(m.group(2)))
            found.append((m.start(), period_key(12, end)))
    out: list[str] = []
    for _, k in sorted(found):
        if k not in out:
            out.append(k)
    return out


def column_period(label: str, form: str, fye: tuple[int, int]) -> str | None:
    p = find_periods(label, fye)
    if p:
        return p[-1]
    years = re.findall(r"\b(20\d\d|19\d\d)\b", label)
    month = re.search(r"\b(" + "|".join(MONTHS) + r") (\d{1,2})\b", label)
    if years and month:  # "June 30, 2025" under a balance-sheet style header
        return f"0M:{date(int(years[-1]), MONTHS[month.group(1)], int(month.group(2))).isoformat()}"
    if years and form.startswith("10-K") and not re.search(r"change", label, re.I):
        return period_key(12, fiscal_year_end(int(years[-1]), fye))
    return None


_NUM = re.compile(r"^\(?\$?\s*-?[\d,]*\.?\d+\s*\)?\s*(%|ppt|pts?)?$")


def parse_number(text: str) -> tuple[float | None, str]:
    t = text.replace("$", "").replace(" ", "").replace("—", "").strip()
    if not t or not _NUM.match(text.replace("$", "").strip()):
        return None, ""
    suffix = ""
    for s in ("%", "ppt", "pts", "pt"):
        if t.endswith(s):
            suffix, t = s, t[: -len(s)]
            break
    neg = t.startswith("(") and t.endswith(")") or t.startswith("(")
    t = t.strip("()").replace(",", "")
    try:
        v = float(t)
    except ValueError:
        return None, ""
    return (-v if neg else v), suffix


def _is_bold(el) -> bool:
    total = bold = 0
    for span in el.iter("span"):
        t = (span.text or "").strip()
        if not t:
            continue
        total += len(t)
        st = (span.get("style") or "").replace(" ", "").lower()
        if "font-weight:bold" in st or "font-weight:700" in st:
            bold += len(t)
    return total > 0 and bold >= 0.9 * total


_RUNNING = re.compile(r"^(PART [IV]+|Items? [0-9A-Z, and]+)$")
_PART = re.compile(r"^PART ([IV]+)\b")
_ITEM = re.compile(r"^ITEM (\d+[A-C]?)\.\s*(.*)$")
_PERIOD_HEADING = re.compile(r"(months ended|fiscal year \d{4}).*compared", re.I)


def _grid(tr) -> list[tuple[int, int, str]]:
    out, col = [], 0
    for td in tr.iter("td", "th"):
        span = int(td.get("colspan") or 1)
        parts = [b.text_content() for b in td if b.tag in ("p", "div")] or [td.text_content()]
        out.append((col, col + span, norm(" ".join(parts))))
        col += span
    return out


def _table_rows(table, form: str, fye: tuple[int, int]):
    """Yield (group, label, cells, note) for each data row of a table."""
    rows = [_grid(tr) for tr in table.iter("tr")]
    rows = [r for r in rows if any(t for _, _, t in r)]
    if not rows:
        return None, []
    note = None
    header: dict[int, list[str]] = {}
    body_start = len(rows)
    for i, r in enumerate(rows):
        texts = [(a, b, t) for a, b, t in r if t]
        nums = [t for a, b, t in texts[1:] if parse_number(t)[0] is not None]
        label_cell = r[0][2] if r else ""
        years_only = nums and all(re.fullmatch(r"(19|20)\d\d", t) for t in nums)
        group_row = header and label_cell and len(texts) == 1 and not label_cell.startswith("(")
        if group_row or nums and label_cell and not label_cell.startswith("(") and not years_only:
            body_start = i
            break
        for a, b, t in texts:
            if t.lower().startswith("(in "):
                note = t
                continue
            for c in range(a, b):
                header.setdefault(c, []).append(t)
    out = []
    group = None
    for r in rows[body_start:]:
        label = r[0][2]
        merged: list[tuple[int, str]] = []
        for a, b, t in r[1:]:
            if not t:
                continue
            if t in ("$",):
                continue
            if t in (")", "%", ")%", "ppt", ")ppt") and merged:
                merged[-1] = (merged[-1][0], merged[-1][1] + t)
                continue
            merged.append((a, t))
        if not merged:
            if label:
                group = label
            continue
        cells = []
        for a, t in merged:
            col = norm(" ".join(dict.fromkeys(header.get(a, []))))
            v, suffix = parse_number(t)
            unit, scale = "", 1.0
            if v is not None:
                if suffix == "%" or "percent" in col.lower() and suffix == "" and "change" in col.lower():
                    unit = "percent"
                elif suffix in ("ppt", "pts", "pt"):
                    unit = "percentage_points"
                elif "per share" in label.lower():
                    unit = "USD/share"
                elif note and "million" in note.lower():
                    unit, scale = "USD", 1_000_000.0
                elif note and "billion" in note.lower():
                    unit, scale = "USD", 1_000_000_000.0
                else:
                    unit = "number"
            cells.append(Cell(column=col, text=t, value=v, unit=unit, scale=scale,
                              period=column_period(col, form, fye) if "change" not in col.lower() else None))
        out.append((group, label, cells))
    return note, out


def _hash(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:10]


def text_fragment_url(url: str, text: str) -> str:
    words = norm(text).split(" ")[:8]
    return f"{url}#:~:text={quote(' '.join(words), safe='')}" if url and words else url


def extract_passages(html: bytes | str, accn: str, form: str, url: str = "",
                     fye: tuple[int, int] = (12, 31)) -> list[Passage]:
    doc = lxml.html.fromstring(html if isinstance(html, bytes) else html.encode("utf-8"))
    body = doc.find("body") if doc.find("body") is not None else doc
    for br in body.iter("br"):  # text_content() drops <br>; keep the word break
        br.tail = " " + (br.tail or "")
    blocks = []
    skip: set = set()
    for el in body.iter():
        if not isinstance(el.tag, str):
            continue
        if el.tag in ("ix:header", "script", "style"):
            skip.update(el.iter())
            continue
        if el in skip:
            continue
        is_list = el.tag == "div" and "item-list-element-wrapper" in (el.get("class") or "")
        if el.tag in ("p", "table") or is_list:
            blocks.append((el, "list" if is_list else el.tag))
            skip.update(el.iter())

    passages: list[Passage] = []
    seen: Counter = Counter()
    part, section, section_title = "", "COVER", "Cover page and table of contents"
    h1 = h2 = subject = None
    period_heading: list[str] = []
    pending: list[Passage] = []
    last_caps = None
    intro_periods: list[str] = []

    def add(kind: str, text: str, **kw) -> None:
        t = norm(text)
        key = (section, kind, t)
        seen[key] += 1
        eid = f"{accn}:{section}:{_hash(accn, section, kind, t, str(seen[key]))}"
        p = Passage(evidence_id=eid, accn=accn, form=form, section=section, section_title=section_title,
                    headings=[h for h in (h1, h2) if h], subject=subject, kind=kind, text=t,
                    url=text_fragment_url(url, kw.pop("anchor", t)), **kw)
        passages.append(p)
        pending.append(p)

    for el, kind in blocks:
        if kind == "table":
            note, rows = _table_rows(el, form, fye)
            title = last_caps or h2 or h1
            for group, label, cells in rows:
                if not label and not cells:
                    continue
                periods = []
                for c in cells:
                    if c.period and c.period not in periods:
                        periods.append(c.period)
                head = f"{group} - {label}" if group else label
                text = f"{head}: " + "; ".join(f"{c.column} {c.text}".strip() for c in cells)
                add("table_row", text, table_title=title, table_note=note, row_label=label, row_group=group,
                    cells=cells, periods=periods, anchor=label or text)
            continue
        text = norm(el.text_content())
        if not text:
            continue
        if re.fullmatch(r"\d{1,3}", text):  # page footer: assign the page to what came before it
            for p in pending:
                p.page = text
            pending.clear()
            continue
        bold = _is_bold(el)
        if not bold and _RUNNING.match(text):
            continue
        if kind == "list":
            # A bullet with no period of its own belongs to the heading above it, or to the
            # sentence that introduced the list ("Highlights from fiscal year 2025 ... included:").
            add("list_item", text.lstrip("•●▪-· ").strip(),
                periods=find_periods(text, fye) or period_heading or intro_periods)
            continue
        m_part, m_item = _PART.match(text), _ITEM.match(text)
        if bold and m_part and len(text) < 60:
            part = m_part.group(1)
            continue
        if bold and m_item:
            section = f"P{part}-I{m_item.group(1)}" if part else f"I{m_item.group(1)}"
            section_title = m_item.group(2).title() or text
            h1 = h2 = subject = last_caps = None
            period_heading = []
            continue
        short = len(text) < 100 and not text.endswith((".", ":", ";"))
        if short and text.isupper() and not bold:
            h1, h2, subject, last_caps, period_heading = text.title(), None, None, text.title(), []
            continue
        if short and bold and _PERIOD_HEADING.search(text):
            period_heading, subject = find_periods(text, fye), None
            continue
        if short and bold:
            h2, subject, period_heading = text, None, []
            last_caps = text
            continue
        if short and len(text) < 70 and text[0].isupper():
            subject = text
            continue
        own = find_periods(text, fye)
        intro_periods = own if text.endswith(":") else []
        add("paragraph", text, periods=period_heading or own)
    return passages
