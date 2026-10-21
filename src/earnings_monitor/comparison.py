"""Compare companies whose fiscal quarters do not line up.

Microsoft's quarters end in Mar/Jun/Sep/Dec, Salesforce's in Jan/Apr/Jul/Oct and Adobe's in
late Feb/May/Aug/Nov (52/53-week years), so no two of them ever cover the same three months.
Rule chosen by Ronin (2026-10-21): for an anchor company's quarter, each other company
contributes its quarter with the largest calendar overlap, and the table always shows the
exact dates, the offset in days, the months shared and the quarter lengths. Only each
company's own changes (growth versus its own prior year) and ratios (margins, conversion) are
put side by side; dollar totals from different windows are never ranked against each other.
Each company's figures are as of that company's own filing date.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from earnings_monitor.analysis import Analysis, CompanyData, analyze
from earnings_monitor.financial_normalization.calendar import FiscalQuarter, FiscalYear

COMPARE_METRICS = [  # (metric id, how it is compared)
    ("revenue", "growth"), ("operating_margin", "level"), ("net_margin", "level"),
    ("free_cash_flow", "growth"), ("cash_conversion", "level"), ("deferred_revenue_current", "growth"),
]
OFFSET_WARN_DAYS = 7  # windows ending more than a week apart are flagged
LENGTH_WARN_DAYS = 3  # quarters whose lengths differ by more than this (13 vs 14 weeks) are flagged


def overlap_days(a_start: date, a_end: date, b_start: date, b_end: date) -> int:
    return max(0, (min(a_end, b_end) - max(a_start, b_start)).days + 1)


def shared_months(a_start: date, a_end: date, b_start: date, b_end: date) -> list[str]:
    """Calendar months in which both windows have at least 15 days."""
    out, d = [], date(max(a_start, b_start).year, max(a_start, b_start).month, 1)
    end = min(a_end, b_end)
    while d <= end:
        nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        last = nxt - timedelta(days=1)
        a = overlap_days(a_start, a_end, d, last)
        b = overlap_days(b_start, b_end, d, last)
        if a >= 15 and b >= 15:
            out.append(f"{d:%b %Y}")
        d = nxt
    return out


@dataclass
class Alignment:
    ticker: str
    start: date
    end: date
    label: str
    length_days: int
    overlap_days: int  # with the anchor window
    offset_days: int  # this window's end minus the anchor's end (negative = ends earlier)
    shared_months: list[str]
    warnings: list[str] = field(default_factory=list)


@dataclass
class CompanyColumn:
    ticker: str
    name: str
    alignment: Alignment
    analysis: Analysis | None
    filing_accn: str | None
    filed: date | None
    values: dict[str, dict] = field(default_factory=dict)  # metric id -> {"value", "prior", "change", "status", "kind"}
    note: str = ""


@dataclass
class CrossCompany:
    basis: str  # "quarter" or "annual"
    anchor: str
    columns: list[CompanyColumn]
    warnings: list[str]


def _window(p) -> tuple[date, date]:
    return p.start, p.end


def align_periods(anchor_ticker: str, anchor, others: dict[str, list]) -> dict[str, Alignment]:
    """For each company, its period (quarter or fiscal year) with the most overlap with the anchor."""
    a_start, a_end = _window(anchor)
    out = {anchor_ticker: Alignment(anchor_ticker, a_start, a_end, anchor.long_label, (a_end - a_start).days + 1,
                                    (a_end - a_start).days + 1, 0, shared_months(a_start, a_end, a_start, a_end))}
    for t, periods in others.items():
        best = max(periods, key=lambda p: (overlap_days(a_start, a_end, *_window(p)), -abs((p.end - a_end).days)),
                   default=None)
        if best is None or overlap_days(a_start, a_end, *_window(best)) == 0:
            continue
        s, e = _window(best)
        al = Alignment(t, s, e, best.long_label, (e - s).days + 1, overlap_days(a_start, a_end, s, e),
                       (e - a_end).days, shared_months(a_start, a_end, s, e))
        anchor_len = (a_end - a_start).days + 1
        if abs(al.offset_days) > OFFSET_WARN_DAYS:
            when = "after" if al.offset_days > 0 else "before"
            al.warnings.append(
                f"{best.long_label} ends {abs(al.offset_days)} days {when} the {anchor_ticker} period "
                f"({a_end:%b %d, %Y}); the two share {al.overlap_days} of {anchor_len} days"
                + (f" ({', '.join(al.shared_months)})" if al.shared_months else "") + ".")
        if abs(al.length_days - anchor_len) > LENGTH_WARN_DAYS:
            al.warnings.append(f"{best.long_label} is {al.length_days} days long; the {anchor_ticker} period is {anchor_len} days.")
        out[t] = al
    return out


def _filing_for(data: CompanyData, end: date, form_prefix: str | None = None) -> tuple[str, date] | None:
    for r in data.filings.sort_values("filed").itertuples():
        if r.report_date is not None and abs((r.report_date - end).days) <= 3 \
                and (form_prefix is None or r.form.startswith(form_prefix)):
            return r.accn, r.filed
    return None


def compare_companies(datasets: dict[str, CompanyData], anchor: str, anchor_end: date, basis: str = "quarter") -> CrossCompany:
    """Side-by-side view of each company's own changes for the period best aligned with the anchor's."""
    cal = datasets[anchor].calendar
    if basis == "annual":
        ap = next((y for y in cal.years if abs((y.end - anchor_end).days) <= 3), None)
        periods = {t: list(d.calendar.years) for t, d in datasets.items() if t != anchor}
    else:
        ap = cal.quarter_ending(anchor_end)
        periods = {t: list(d.calendar.quarters) for t, d in datasets.items() if t != anchor}
    if ap is None:
        raise ValueError(f"{anchor} has no {basis} period ending {anchor_end}")
    al = align_periods(anchor, ap, periods)
    cols, warnings = [], []
    for t, data in datasets.items():
        if t not in al:
            warnings.append(f"{t}: no {basis} period overlaps the {anchor} period.")
            continue
        a = al[t]
        f = _filing_for(data, a.end, "10-K" if basis == "annual" else None)
        col = CompanyColumn(t, data.company.name, a, None, f[0] if f else None, f[1] if f else None)
        if f is None:
            col.note = f"No filing for {a.label} yet; the period is known from other filings' comparative figures."
        else:
            res = analyze(data, f[0], "annual" if basis == "annual" else "yoy")
            col.analysis = res
            by = {c.metric_id: c for c in res.changes}
            for m, kind in COMPARE_METRICS:
                c = by.get(m)
                if c is None:
                    continue
                col.values[m] = {"label": c.metric_label, "kind": kind, "unit": c.unit,
                                 "value": c.current.value, "prior": c.prior.value, "status": c.current.status,
                                 "change": c.pct_change if kind == "growth" else c.abs_change,
                                 "change_kind": "percent" if kind == "growth" else "percentage_points"}
        cols.append(col)
        warnings.extend(f"{t}: {w}" for w in a.warnings)
    if basis == "quarter":
        warnings.append("Quarterly cash flows are seasonal and these windows differ; compare each company with its "
                        "own prior year before comparing companies.")
    return CrossCompany(basis, anchor, cols, warnings)
