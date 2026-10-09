"""Analyze one filing: select values as of its filing date, compare periods, check, flag."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from earnings_monitor.calculations.flags import evaluate
from earnings_monitor.calculations.measures import MEASURE_DEFINITIONS, compare, period_measures
from earnings_monitor.config import Company
from earnings_monitor.financial_normalization.calendar import FiscalCalendar, FiscalQuarter
from earnings_monitor.financial_normalization.metrics import DISPLAY_METRICS, METRICS
from earnings_monitor.financial_normalization.selection import FactSelector
from earnings_monitor.models import Change, Finding, Issue, MetricValue, filing_url
from earnings_monitor.validation import checks

COMPARISONS = {
    "sequential": "Sequential quarter (vs previous quarter)",
    "yoy": "Same quarter, prior fiscal year",
    "annual": "Full fiscal year vs prior fiscal year",
}

ROW_ORDER = [
    "revenue", "operating_income", "operating_margin", "net_income", "net_margin",
    "operating_cash_flow", "capex", "free_cash_flow", "cash_conversion",
    "cash", "accounts_receivable", "deferred_revenue_current", "deferred_revenue_noncurrent",
    "debt_current", "debt_noncurrent", "total_debt",
]

TREND_METRICS = ["revenue", "operating_income", "net_income", "operating_cash_flow", "free_cash_flow",
                 "operating_margin", "net_margin", "cash", "accounts_receivable", "deferred_revenue_current", "total_debt"]


@dataclass
class CompanyData:
    company: Company
    obs: pd.DataFrame
    filings: pd.DataFrame  # accn, form, filed, report_date, primary_document
    calendar: FiscalCalendar
    data_source: str  # "sec" or "fixture"
    raw_sha256: str
    fetched_at: str
    fiscal_year_end: str | None = None  # "MMDD" from submissions, when available

    def primary_documents(self) -> dict[str, str]:
        return {r.accn: r.primary_document for r in self.filings.itertuples() if r.primary_document}


@dataclass
class FilingInfo:
    accn: str
    form: str
    filed: date
    report_date: date | None
    url: str


@dataclass
class Analysis:
    company: Company
    filing: FilingInfo
    as_of: date
    quarter: FiscalQuarter
    comparison: str
    comparison_label: str
    current_label: str
    prior_label: str
    changes: list[Change]
    findings: list[Finding]
    issues: list[Issue]
    trend: pd.DataFrame
    data_source: str
    raw_sha256: str
    fetched_at: str
    all_values: list[MetricValue] = field(default_factory=list)


class AnalysisError(ValueError):
    pass


def filing_info(data: CompanyData, accn: str) -> FilingInfo:
    row = data.filings[data.filings["accn"] == accn]
    if row.empty:
        raise AnalysisError(f"Unknown filing {accn}")
    r = row.iloc[0]
    rd = r["report_date"] if pd.notna(r["report_date"]) else None
    return FilingInfo(accn, r["form"], r["filed"], rd, filing_url(data.company.cik, accn, r["primary_document"] or None))


def filing_quarter(data: CompanyData, f: FilingInfo) -> FiscalQuarter:
    end = f.report_date
    if end is None:
        ends = data.obs[(data.obs["accn"] == f.accn) & (data.obs["taxonomy"] == "us-gaap")]["end"]
        if ends.empty:
            raise AnalysisError(f"No facts found for filing {f.accn}")
        end = ends.max()
    q = data.calendar.quarter_ending(end)
    if q is None:
        raise AnalysisError(f"Filing {f.accn} reports a period ending {end} that is not a known fiscal quarter end.")
    return q


def available_comparisons(data: CompanyData, accn: str) -> list[str]:
    f = filing_info(data, accn)
    out = ["sequential", "yoy"]
    if f.form.startswith("10-K"):
        out.append("annual")
    return out


def _values_for(sel: FactSelector, getter) -> dict[str, MetricValue]:
    vals = {m: getter(METRICS[m]) for m in DISPLAY_METRICS}
    vals.update(period_measures(vals))
    return vals


def analyze(data: CompanyData, accn: str, comparison: str = "yoy") -> Analysis:
    if comparison not in COMPARISONS:
        raise AnalysisError(f"Unknown comparison {comparison}")
    f = filing_info(data, accn)
    q = filing_quarter(data, f)
    cal = data.calendar
    sel = FactSelector(data.obs, data.company, f.filed, data.primary_documents())
    issues: list[Issue] = []

    if comparison == "annual":
        if not f.form.startswith("10-K"):
            raise AnalysisError("Annual comparison is only valid for a 10-K filing.")
        fy, prior_fy = cal.year(q.fiscal_year), cal.year(q.fiscal_year - 1)
        if fy is None or prior_fy is None:
            raise AnalysisError("Fiscal year or prior fiscal year not found in the reported data.")
        cur = _values_for(sel, lambda m: sel.annual_value(m, fy))
        pri = _values_for(sel, lambda m: sel.annual_value(m, prior_fy))
        cur_label, pri_label = fy.long_label, prior_fy.long_label
    else:
        pq = cal.previous_quarter(q) if comparison == "sequential" else cal.same_quarter_prior_year(q)
        if pq is None:
            raise AnalysisError(f"No comparable prior period for {q.long_label} ({COMPARISONS[comparison]}).")
        cur = _values_for(sel, lambda m: sel.quarter_value(m, q, cal))
        pri = _values_for(sel, lambda m: sel.quarter_value(m, pq, cal))
        cur_label, pri_label = q.long_label, pq.long_label
        issues.append(checks.balance_sheet_identity(sel, pq))
        issues.extend(checks.ytd_consistency(sel, cal, pq))
    issues.insert(0, checks.balance_sheet_identity(sel, q))
    issues.extend(checks.ytd_consistency(sel, cal, q))

    label = COMPARISONS[comparison]
    changes = [compare(cur[m], pri[m], label) for m in ROW_ORDER if m in cur and m in pri]
    by_id = {c.metric_id: c for c in changes}
    findings = evaluate(by_id, label)
    all_values = list(cur.values()) + list(pri.values())
    issues.extend(checks.value_issues(all_values))
    issues.extend(checks.change_issues(changes))
    if data.data_source == "fixture":
        issues.insert(0, Issue(severity="warning", code="fixture_mode",
                               message="FIXTURE MODE: data was loaded from local files, not downloaded from SEC in this run."))

    trend = build_trend(sel, cal, q)
    return Analysis(data.company, f, f.filed, q, comparison, label, cur_label, pri_label, changes, findings,
                    issues, trend, data.data_source, data.raw_sha256, data.fetched_at, all_values)


def build_trend(sel: FactSelector, cal: FiscalCalendar, q: FiscalQuarter, n: int = 12) -> pd.DataFrame:
    rows = []
    for pq in cal.quarters_through(q, n):
        vals = _values_for(sel, lambda m: sel.quarter_value(m, pq, cal))
        for m in TREND_METRICS:
            v = vals[m]
            rows.append({"metric_id": m, "metric_label": v.metric_label, "unit": v.unit,
                         "period_label": pq.label, "period_long_label": pq.long_label, "period_end": pq.end,
                         "value": v.value, "status": v.status})
    return pd.DataFrame(rows)


def metric_label(metric_id: str) -> str:
    if metric_id in METRICS:
        return METRICS[metric_id].label
    return MEASURE_DEFINITIONS[metric_id][0]
