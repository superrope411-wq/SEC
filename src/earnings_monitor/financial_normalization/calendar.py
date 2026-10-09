"""Build each company's fiscal calendar from the period dates it actually reported.

We never trust the `fy`/`fp` fields to say which period a number belongs to: in companyfacts
they describe the filing a fact came from, so a prior-year comparative inside a FY2025 10-Q
is also tagged fy=2025. Periods are identified by start/end dates instead.

Fiscal years come from annual (350-380 day) duration facts in 10-K filings. Quarter ends
within a fiscal year are the distinct end dates of year-to-date facts that start on the
fiscal-year start date (3, 6, 9 and 12 months). This works for June, January and
52/53-week fiscal years alike.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

ANNUAL_DAYS = (350, 380)
QUARTER_DAYS = (80, 100)


@dataclass(frozen=True)
class FiscalQuarter:
    fiscal_year: int
    quarter: int  # 1-4
    start: date
    end: date
    fy_start: date
    fy_end: date | None  # None while the fiscal year is still in progress

    @property
    def label(self) -> str:
        return f"FY{self.fiscal_year} Q{self.quarter}"

    @property
    def long_label(self) -> str:
        return f"{self.label} ({_months(self.start, self.end)})"


@dataclass(frozen=True)
class FiscalYear:
    fiscal_year: int
    start: date
    end: date

    @property
    def label(self) -> str:
        return f"FY{self.fiscal_year}"

    @property
    def long_label(self) -> str:
        return f"{self.label} ({_months(self.start, self.end)})"


def _months(start: date, end: date) -> str:
    # A 52/53-week period can start a few days before the month it mostly covers.
    s = start + timedelta(days=7) if start.day > 20 else start
    if s.year == end.year:
        return f"{s:%b}–{end:%b %Y}"
    return f"{s:%b %Y}–{end:%b %Y}"


class FiscalCalendar:
    def __init__(self, years: list[FiscalYear], quarters: list[FiscalQuarter]):
        self.years = sorted(years, key=lambda y: y.end)
        self.quarters = sorted(quarters, key=lambda q: q.end)

    def quarter_ending(self, end: date, tolerance_days: int = 3) -> FiscalQuarter | None:
        best = None
        for q in self.quarters:
            gap = abs((q.end - end).days)
            if gap <= tolerance_days and (best is None or gap < abs((best.end - end).days)):
                best = q
        return best

    def previous_quarter(self, q: FiscalQuarter) -> FiscalQuarter | None:
        idx = self.quarters.index(q)
        if idx == 0:
            return None
        prev = self.quarters[idx - 1]
        # Only adjacent if there is no gap in the calendar.
        return prev if (q.start - prev.end).days == 1 else None

    def same_quarter_prior_year(self, q: FiscalQuarter) -> FiscalQuarter | None:
        for c in self.quarters:
            if c.fiscal_year == q.fiscal_year - 1 and c.quarter == q.quarter:
                return c
        return None

    def year(self, fiscal_year: int) -> FiscalYear | None:
        return next((y for y in self.years if y.fiscal_year == fiscal_year), None)

    def quarters_through(self, q: FiscalQuarter, n: int) -> list[FiscalQuarter]:
        idx = self.quarters.index(q)
        return self.quarters[max(0, idx - n + 1): idx + 1]


def build_calendar(obs: pd.DataFrame) -> FiscalCalendar:
    dur = obs[(obs["period_type"] == "duration") & obs["form"].str.startswith("10-")]

    annual = dur[dur["duration_days"].between(*ANNUAL_DAYS) & dur["form"].str.startswith("10-K")]
    # Count how many facts use each (start, end) pair; real fiscal years are used by many facts.
    counts = Counter(zip(annual["start"], annual["end"]))
    fy_periods: list[tuple[date, date]] = []
    for (s, e), n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0][1])):
        if n < 3:
            continue
        if any(s <= pe and e >= ps for ps, pe in fy_periods):
            continue  # overlaps a better-supported fiscal year
        fy_periods.append((s, e))
    fy_periods.sort(key=lambda p: p[1])

    years: list[FiscalYear] = []
    quarters: list[FiscalQuarter] = []
    spans: list[tuple[date, date | None]] = list(fy_periods)
    if fy_periods:
        open_start = fy_periods[-1][1] + timedelta(days=1)
        if (dur["start"] == open_start).any():
            spans.append((open_start, None))

    for s, e in spans:
        label = _fiscal_year_label(obs, s, e)
        if e is not None:
            years.append(FiscalYear(label, s, e))
        ytd = dur[(dur["start"] == s)]
        if e is not None:
            ytd = ytd[ytd["end"] <= e]
        ends = sorted(set(ytd[ytd["duration_days"] >= QUARTER_DAYS[0]]["end"]))
        ends = _plausible_quarter_ends(s, ends)
        prev_end = s - timedelta(days=1)
        for i, qe in enumerate(ends, start=1):
            quarters.append(FiscalQuarter(label, i, prev_end + timedelta(days=1), qe, s, e))
            prev_end = qe
    return FiscalCalendar(years, quarters)


def _plausible_quarter_ends(fy_start: date, ends: list[date]) -> list[date]:
    """Keep at most one end date near each of 3, 6, 9 and 12 months from the fiscal-year start."""
    picked = []
    for k in range(1, 5):
        target = 91.3 * k
        near = [e for e in ends if abs(((e - fy_start).days + 1) - target) <= 20]
        if near:
            picked.append(min(near, key=lambda e: abs(((e - fy_start).days + 1) - target)))
    return picked


def _fiscal_year_label(obs: pd.DataFrame, start: date, end: date | None) -> int:
    """Use the company's own fiscal-year number: the `fy` of filings whose own reporting
    period falls inside this fiscal year. Fall back to the end-date year."""
    o = obs[obs["fy"].notna()]
    report_end = o.groupby("accn")["end"].max()
    own = o[o["end"] == o["accn"].map(report_end)]
    in_year = (own["end"] >= start) & ((own["end"] <= end) if end else True)
    fys = own[in_year]["fy"]
    if len(fys):
        return int(Counter(fys).most_common(1)[0][0])
    if end is not None:
        return end.year
    return (start + timedelta(days=364)).year
