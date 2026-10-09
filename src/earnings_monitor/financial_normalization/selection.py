"""Fact selection: turn many original observations into one value per metric and period.

Rules (see docs/FACT_SELECTION_POLICY.md):
1. Point in time: only facts from 10-K/10-Q filings (and amendments) filed on or before the
   as-of date are eligible, so later restatements cannot leak into a historical analysis.
2. Concept must be one of the metric's approved concepts, in the approved taxonomy and unit.
   companyfacts contains only non-dimensional facts, so every eligible fact is a
   consolidated total, never a segment.
3. Period must match exactly (start and end for durations, end date for instants).
4. Among eligible facts for the same concept and period, use the most recently filed one
   (what the company was reporting as of that date) and record the originally reported value.
5. Approved concepts are tried in order; disagreement with a lower-ranked concept is recorded.
6. Standalone quarters are derived from year-to-date facts only when both facts share the
   same concept and the same fiscal-year start date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from earnings_monitor.config import Company
from earnings_monitor.financial_normalization.calendar import FiscalCalendar, FiscalQuarter, FiscalYear
from earnings_monitor.financial_normalization.metrics import Metric
from earnings_monitor.financial_normalization.observations import ALLOWED_FORMS
from earnings_monitor.models import MetricValue, SourceRef, filing_url


@dataclass
class Selected:
    value: float
    concept: str
    row: pd.Series
    reason: str
    restated: bool
    original_value: float
    original_row: pd.Series
    notes: list[str]


class FactSelector:
    def __init__(self, obs: pd.DataFrame, company: Company, as_of: date, primary_documents: dict[str, str] | None = None):
        self.company = company
        self.as_of = as_of
        self.primary_documents = primary_documents or {}
        self.obs = obs[obs["form"].isin(ALLOWED_FORMS) & (obs["filed"] <= as_of)]
        self._by_concept = {c: g for c, g in self.obs.groupby("concept")}

    # ---- low level -------------------------------------------------------------------------

    def source_ref(self, row: pd.Series) -> SourceRef:
        return SourceRef(
            obs_id=row["obs_id"], taxonomy=row["taxonomy"], concept=row["concept"], unit=row["unit"],
            value=float(row["value"]), period_start=row["start"], period_end=row["end"],
            accn=row["accn"], form=row["form"], filed=row["filed"],
            url=filing_url(self.company.cik, row["accn"], self.primary_documents.get(row["accn"])),
        )

    def _rows(self, metric: Metric, concept: str, start: date | None, end: date) -> pd.DataFrame:
        g = self._by_concept.get(concept)
        if g is None:
            return g
        g = g[(g["taxonomy"] == metric.taxonomy) & (g["unit"] == metric.unit) & (g["end"] == end)]
        if metric.period_type == "instant":
            return g[g["period_type"] == "instant"]
        return g[(g["period_type"] == "duration") & (g["start"] == start)]

    def select_exact(self, metric: Metric, start: date | None, end: date) -> tuple[Selected | None, list[str]]:
        """Return the selected fact for an exact period, plus notes explaining any absence."""
        chosen: Selected | None = None
        notes: list[str] = []
        period = f"{start}..{end}" if start else f"at {end}"
        for rank, concept in enumerate(metric.concepts, start=1):
            rows = self._rows(metric, concept, start, end)
            if rows is None or rows.empty:
                continue
            rows = rows.sort_values(["filed", "accn"])
            latest = rows.iloc[-1]
            first = rows.iloc[0]
            same_filing = rows[rows["accn"] == latest["accn"]]
            if same_filing["value"].nunique() > 1:
                notes.append(
                    f"{concept}: filing {latest['accn']} reports {same_filing['value'].nunique()} different values "
                    f"for {period}; used the first listed. Needs manual review."
                )
            if chosen is None:
                restated = float(first["value"]) != float(latest["value"])
                n_filings = rows["accn"].nunique()
                reason = (
                    f"{metric.taxonomy}:{concept} is approved concept #{rank} for {metric.label}; unit {metric.unit}; "
                    f"consolidated (non-dimensional) fact; exact period {period}; "
                    f"most recent value filed on or before {self.as_of} "
                    f"({latest['form']} {latest['accn']}, filed {latest['filed']}). "
                    f"Reported in {n_filings} filing(s) up to that date."
                )
                if restated:
                    reason += (
                        f" Originally reported as {float(first['value']):,.0f} in {first['form']} {first['accn']} "
                        f"(filed {first['filed']}); later revised."
                    )
                chosen = Selected(float(latest["value"]), concept, latest, reason, restated,
                                  float(first["value"]), first, [])
            else:
                if float(latest["value"]) != chosen.value:
                    notes.append(
                        f"Lower-ranked concept {concept} reports {float(latest['value']):,.0f} for {period}, "
                        f"which differs from the selected {chosen.concept} ({chosen.value:,.0f})."
                    )
        if chosen is not None:
            chosen.notes = notes
        else:
            notes.append(
                f"No {metric.taxonomy} fact for {', '.join(metric.concepts)} in {metric.unit} for {period} "
                f"in a 10-K/10-Q filed on or before {self.as_of}. Shown as missing, not zero."
            )
        return chosen, notes

    def _value(self, metric: Metric, basis: str, start, end, label, sel: Selected | None, notes: list[str]) -> MetricValue:
        common = dict(
            company=self.company.ticker, cik=self.company.cik, metric_id=metric.id, metric_label=metric.label,
            unit=metric.unit, period_type=metric.period_type, basis=basis,
            period_start=start, period_end=end, period_label=label,
        )
        if sel is None:
            return MetricValue(**common, value=None, status="missing", notes=notes,
                               selection_reason="No eligible fact; see notes.")
        return MetricValue(
            **common, value=sel.value, status="reported", concept=sel.concept,
            sources=[self.source_ref(sel.row)], selection_reason=sel.reason, notes=sel.notes,
            restated=sel.restated, originally_reported=sel.original_value if sel.restated else None,
        )

    # ---- public ----------------------------------------------------------------------------

    def instant_value(self, metric: Metric, at: date, label: str) -> MetricValue:
        sel, notes = self.select_exact(metric, None, at)
        return self._value(metric, "instant", None, at, label, sel, notes)

    def annual_value(self, metric: Metric, fy: FiscalYear) -> MetricValue:
        if metric.period_type == "instant":
            return self.instant_value(metric, fy.end, fy.long_label)
        sel, notes = self.select_exact(metric, fy.start, fy.end)
        return self._value(metric, "annual", fy.start, fy.end, fy.long_label, sel, notes)

    def quarter_value(self, metric: Metric, q: FiscalQuarter, cal: FiscalCalendar) -> MetricValue:
        if metric.period_type == "instant":
            return self.instant_value(metric, q.end, q.long_label)
        direct, notes = self.select_exact(metric, q.start, q.end)
        if direct is not None or q.quarter == 1:
            return self._value(metric, "quarter", q.start, q.end, q.long_label, direct, notes)

        # Derive the standalone quarter from year-to-date figures.
        prev_q = cal.previous_quarter(q)
        base = self._value(metric, "quarter", q.start, q.end, q.long_label, None, [])
        if prev_q is None or prev_q.fy_start != q.fy_start:
            base.notes = notes + ["Cannot derive: previous quarter in the same fiscal year is unknown."]
            return base
        cur, n1 = self.select_exact(metric, q.fy_start, q.end)
        prev, n2 = self.select_exact(metric, q.fy_start, prev_q.end)
        cur_name = "FY" if (q.quarter == 4 and q.fy_end == q.end) else f"YTD through Q{q.quarter}"
        prev_name = f"YTD through Q{prev_q.quarter}"
        if cur is None or prev is None:
            missing = cur_name if cur is None else prev_name
            base.notes = notes + [f"No direct 3-month fact, and {missing} ({q.fy_start}..{(q.end if cur is None else prev_q.end)}) is not available to derive it."]
            return base
        if cur.concept != prev.concept:
            base.notes = notes + [
                f"Not derived: {cur_name} uses {cur.concept} but {prev_name} uses {prev.concept}; "
                "subtracting different concepts would not be a valid quarter."
            ]
            return base
        value = cur.value - prev.value
        restated = cur.restated or prev.restated
        return MetricValue(
            company=self.company.ticker, cik=self.company.cik, metric_id=metric.id, metric_label=metric.label,
            unit=metric.unit, period_type="duration", basis="quarter",
            period_start=q.start, period_end=q.end, period_label=q.long_label,
            value=value, status="derived", concept=cur.concept,
            formula=f"{cur_name} − {prev_name}",
            input_values={f"{cur_name} ({q.fy_start}..{q.end})": cur.value,
                          f"{prev_name} ({q.fy_start}..{prev_q.end})": prev.value},
            sources=[self.source_ref(cur.row), self.source_ref(prev.row)],
            selection_reason=(
                f"No 3-month fact was filed for {q.start}..{q.end}, so the quarter is derived from two "
                f"year-to-date facts with the same concept ({cur.concept}) and the same fiscal-year start "
                f"({q.fy_start}). [{cur_name}] {cur.reason} [{prev_name}] {prev.reason}"
            ),
            notes=notes[:-1] + n1 + n2 if notes else n1 + n2,
            restated=restated,
        )
