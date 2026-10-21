"""Check a number quoted from the filing against the verified calculations.

A figure passes only if all four agree:
  metric  - the number is about the metric itself (row "Revenue"/"Total", or a sentence whose
            subject is "Revenue"), not a segment or product line ("Intelligent Cloud revenue");
  period  - the passage's period context (table column, or the "Fiscal Year 2025 Compared with
            Fiscal Year 2024" style heading above it) is the analyzed period (and prior period);
  unit    - dollars for amounts, percent for percent changes, with the printed scale applied
            ("$36.6 billion", or "281,724" under "(In millions)");
  value   - the printed number equals the pipeline's number to the printed precision
            ($36.6 billion vs 36,602M passes; 15% vs 14.93% passes), and the stated direction
            ("increased"/"decreased") matches the sign.
Finding the same digits somewhere in the document is never enough.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from earnings_monitor.evidence.extract import Passage, norm, period_key
from earnings_monitor.evidence.vocab import METRIC_TERMS
from earnings_monitor.explain.schema import CalculatedChange, Figure, FigureCheck

_SCALE = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
_MONEY = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s?(thousand|million|billion|trillion)?", re.I)
_PCT = re.compile(r"\(?(\d[\d,]*(?:\.\d+)?)\)?\s?(%|percent\b|percentage points?|points?\b|ppt)", re.I)
_UP = re.compile(r"\b(increased|increase|grew|growth|rose|up|higher|improved)\b", re.I)
_DOWN = re.compile(r"\b(decreased|decrease|declined|decline|fell|down|lower|reduced)\b", re.I)


@dataclass
class Mention:
    text: str
    value: float  # whole units (dollars, or percent points for percentages)
    unit: str  # "USD" | "percent" | "percentage_points"
    tolerance: float
    sentence: str
    before: str  # sentence text before the number


def _decimals(s: str) -> int:
    return len(s.split(".")[1]) if "." in s else 0


def _sentences(text: str) -> list[tuple[int, str]]:
    out, start = [], 0
    for m in re.finditer(r"(?<=[a-z0-9%)])\.\s+(?=[A-Z])", text):
        out.append((start, text[start:m.start() + 1]))
        start = m.end()
    out.append((start, text[start:]))
    return out


def mentions(text: str) -> list[Mention]:
    text = norm(text)
    found = []
    for off, sent in _sentences(text):
        for m in _MONEY.finditer(sent):
            digits, scale = m.group(1).replace(",", ""), _SCALE.get((m.group(2) or "").lower(), 1.0)
            tol = 0.5 * 10 ** (-_decimals(digits)) * scale
            found.append(Mention(m.group(0), float(digits) * scale, "USD", tol, sent, sent[:m.start()]))
        for m in _PCT.finditer(sent):
            digits = m.group(1).replace(",", "")
            unit = "percent" if m.group(2) in ("%",) or m.group(2).lower() == "percent" else "percentage_points"
            v = float(digits) * (-1 if m.group(0).startswith("(") else 1)
            found.append(Mention(m.group(0), v, unit, 0.5 * 10 ** (-_decimals(digits)), sent, sent[:m.start()]))
    return found


def _same_number(stated: str, printed: str) -> bool:
    clean = lambda s: re.sub(r"[\s$]", "", norm(s)).lower().replace("percent", "%")
    return clean(stated) == clean(printed)


def _target_periods(c: CalculatedChange, cur_start, cur_end, pri_start, pri_end, basis: str) -> tuple[str, str]:
    if basis == "instant":
        return f"0M:{cur_end.isoformat()}", f"0M:{pri_end.isoformat()}"
    months = lambda s, e: round(((e - s).days + 1) / 30.4)
    return period_key(months(cur_start, cur_end), cur_end), period_key(months(pri_start, pri_end), pri_end)


def _is_total_row(p: Passage, metric_id: str) -> bool:
    terms = METRIC_TERMS.get(metric_id, [])
    label = (p.row_label or "").lower()
    group = (p.row_group or "").lower()
    if group in ("", "total") and label in terms:
        return True
    return label == "total" and group in terms  # e.g. group "Revenue", row "Total"


def _subject_is_metric(before: str, metric_id: str, subject: str | None) -> tuple[bool, str]:
    """The metric phrase must be the sentence's subject: at the start, or after 'total'."""
    if subject:
        return False, f"passage is about '{subject}', not the company total"
    low = before.lower()
    best = None
    for term in METRIC_TERMS.get(metric_id, []):
        for m in re.finditer(rf"(^|[^a-z]){re.escape(term)}([^a-z]|$)", low):
            best = max(best or -1, m.start())
            pre = before[:m.start() + (1 if m.group(1) else 0)].strip()
            if pre in ("", "Total", "total", "Our", "our", "Our total", "our total"):
                return True, ""
    if best is None:
        return False, "the sentence does not name this metric before the number"
    return False, "the metric is qualified by other words (a segment, product or sub-total)"


def check_figure(fig: Figure, p: Passage | None, c: CalculatedChange | None, periods: tuple[str, str]) -> FigureCheck:
    out = FigureCheck(figure=fig, result="rejected")
    if p is None:
        out.reasons.append("evidence ID does not resolve to a passage of this filing")
        return out
    if c is None:
        out.result = "unchecked"
        out.reasons.append(f"'{fig.metric_id}' is not one of the calculated metrics; number not checked")
        return out
    cur_key, pri_key = periods
    if fig.measure == "current_value":
        expected, want_unit = c.current_value, "USD" if c.unit == "USD" else "ratio"
    elif fig.measure == "prior_value":
        expected, want_unit = c.prior_value, "USD" if c.unit == "USD" else "ratio"
    elif fig.measure == "change_amount":
        expected = c.change_amount
        want_unit = "USD" if c.unit == "USD" else "percentage_points"
    else:
        expected = None if c.change_percent is None else c.change_percent * 100
        want_unit = "percent"
    out.expected = expected
    if expected is None:
        out.result = "unchecked"
        out.reasons.append("no calculated value for this measure")
        return out

    if p.kind == "table_row":
        cells = [x for x in p.cells if _same_number(fig.stated_text, x.text)]
        if not cells:
            out.reasons.append(f"'{fig.stated_text}' is not a cell of this table row")
            return out
        if not _is_total_row(p, fig.metric_id):
            out.reasons.append(f"metric: row '{p.row_group + ' - ' if p.row_group else ''}{p.row_label}' is not total {c.metric_label.lower()}")
            return out
        want_period = {"current_value": cur_key, "prior_value": pri_key}.get(fig.measure)
        if want_period:
            cells = [x for x in cells if x.period == want_period]
            if not cells:
                out.reasons.append(f"period: no column for {want_period} holds '{fig.stated_text}'")
                return out
        elif not (cur_key in p.periods and pri_key in p.periods):
            out.reasons.append(f"period: table compares {p.periods}, not {cur_key} vs {pri_key}")
            return out
        else:  # a change column: it must be the one right after the current-period column
            idx = [i for i, x in enumerate(p.cells) if x.period == cur_key]
            ok = [x for x in cells if idx and p.cells.index(x) > idx[0] and x.period is None
                  and all(y.period is not None for y in p.cells[idx[0]:p.cells.index(x)])]
            if not ok:
                out.reasons.append("period: the percent-change cell is not the one for the analyzed comparison")
                return out
            cells = ok
        cell = cells[0]
        unit = cell.unit
        stated = cell.value * cell.scale if unit == "USD" else cell.value
        tol = 0.5 * cell.scale if unit == "USD" else 0.5
    else:
        ms = [m for m in mentions(p.text) if _same_number(fig.stated_text, m.text)]
        if not ms:
            out.reasons.append(f"'{fig.stated_text}' does not appear in the passage as a dollar amount or percentage")
            return out
        m = ms[0]
        ok, why = _subject_is_metric(m.before, fig.metric_id, p.subject)
        if not ok:
            out.reasons.append("metric: " + why)
            return out
        need = [cur_key] if fig.measure == "current_value" else [pri_key] if fig.measure == "prior_value" else [cur_key, pri_key]
        if fig.measure in ("change_amount", "change_percent"):
            good = p.periods[:2] == need or (p.periods[:1] == [cur_key] and len(p.periods) == 1)
        else:
            good = all(k in p.periods for k in need)
        if not good:
            out.reasons.append(f"period: passage is about {p.periods or 'no stated period'}, not {' vs '.join(need)}")
            return out
        unit, stated, tol = m.unit, m.value, m.tolerance
        if fig.measure in ("change_amount", "change_percent"):
            ups = [x.end() for x in _UP.finditer(m.before)]
            downs = [x.end() for x in _DOWN.finditer(m.before)]
            if downs and (not ups or downs[-1] > ups[-1]):  # the nearest verb before the number wins
                stated = -abs(stated)
    if unit != want_unit and not (want_unit == "percentage_points" and unit == "percent"):
        out.reasons.append(f"unit: printed as {unit or 'unknown'}, the {fig.measure.replace('_', ' ')} is {want_unit}")
        return out
    out.stated = stated
    if abs(stated - expected) <= tol + 1e-9 * max(abs(expected), 1):
        out.result = "verified"
        return out
    out.result = "conflict"
    out.reasons.append(f"value: filing says {fig.stated_text} ({stated:,.4g}), verified calculation is {expected:,.4g}")
    return out
