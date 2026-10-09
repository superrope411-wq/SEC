"""Consistency checks run on every analysis. Failures are shown to the analyst, never hidden."""

from __future__ import annotations

from earnings_monitor.financial_normalization.calendar import FiscalCalendar, FiscalQuarter
from earnings_monitor.financial_normalization.metrics import METRICS
from earnings_monitor.financial_normalization.selection import FactSelector
from earnings_monitor.models import Change, Issue, MetricValue

BALANCE_TOLERANCE = 0.005  # 0.5% of total assets


def balance_sheet_identity(sel: FactSelector, q: FiscalQuarter) -> Issue:
    a = sel.instant_value(METRICS["assets"], q.end, q.long_label)
    le = sel.instant_value(METRICS["liabilities_and_equity"], q.end, q.long_label)
    if not (a.is_available and le.is_available):
        return Issue(severity="warning", code="balance_identity_unchecked", period_label=q.long_label,
                     message="Could not check assets = liabilities + equity: a total is missing.")
    gap = abs(a.value - le.value) / abs(a.value) if a.value else 1.0
    if gap > BALANCE_TOLERANCE:
        return Issue(severity="error", code="balance_identity_failed", period_label=q.long_label,
                     message=f"Total assets ({a.value:,.0f}) differ from liabilities + equity ({le.value:,.0f}) by {gap:.2%}.")
    return Issue(severity="info", code="balance_identity_ok", period_label=q.long_label,
                 message=f"Assets equal liabilities + equity ({a.value:,.0f}).")


def ytd_consistency(sel: FactSelector, cal: FiscalCalendar, q: FiscalQuarter) -> list[Issue]:
    """Where a 3-month fact exists for Q2/Q3, check it equals the difference of the YTD facts."""
    issues: list[Issue] = []
    prev = cal.previous_quarter(q)
    if q.quarter == 1 or prev is None or prev.fy_start != q.fy_start:
        return issues
    for m in METRICS.values():
        if m.period_type != "duration":
            continue
        direct, _ = sel.select_exact(m, q.start, q.end)
        cur, _ = sel.select_exact(m, q.fy_start, q.end)
        before, _ = sel.select_exact(m, q.fy_start, prev.end)
        if not (direct and cur and before) or cur.concept != before.concept:
            continue
        derived = cur.value - before.value
        if abs(derived - direct.value) > max(1.0, abs(direct.value) * 1e-6):
            issues.append(Issue(severity="error", code="ytd_mismatch", metric_id=m.id, period_label=q.long_label,
                                message=f"{m.label}: reported quarter {direct.value:,.0f} ≠ YTD difference {derived:,.0f}."))
        else:
            issues.append(Issue(severity="info", code="ytd_consistent", metric_id=m.id, period_label=q.long_label,
                                message=f"{m.label}: reported quarter matches YTD difference."))
    return issues


def value_issues(values: list[MetricValue]) -> list[Issue]:
    issues: list[Issue] = []
    seen: set[tuple[str, str]] = set()
    for v in values:
        key = (v.metric_id, v.period_label)
        if key in seen:
            continue
        seen.add(key)
        if v.status == "missing":
            issues.append(Issue(severity="warning", code="missing", metric_id=v.metric_id, period_label=v.period_label,
                                message=f"{v.metric_label} missing for {v.period_label}. " + " ".join(v.notes)))
        if v.status == "not_meaningful":
            issues.append(Issue(severity="info", code="not_meaningful", metric_id=v.metric_id, period_label=v.period_label,
                                message=f"{v.metric_label} for {v.period_label}: " + " ".join(v.notes)))
        if v.restated:
            issues.append(Issue(severity="warning", code="restated", metric_id=v.metric_id, period_label=v.period_label,
                                message=f"{v.metric_label} for {v.period_label} was revised after first being reported. "
                                        "Value shown is the latest available as of this filing date. XBRL data does not say "
                                        "why (accounting-policy change or error correction); see the filing."))
        for n in v.notes:
            if "different values" in n:
                issues.append(Issue(severity="error", code="conflicting_duplicates", metric_id=v.metric_id,
                                    period_label=v.period_label, message=n))
            elif "Lower-ranked concept" in n:
                issues.append(Issue(severity="warning", code="concept_disagreement", metric_id=v.metric_id,
                                    period_label=v.period_label, message=n))
        if v.is_available and v.metric_id in {"capex", "revenue"} and v.value < 0:
            issues.append(Issue(severity="warning", code="unexpected_sign", metric_id=v.metric_id, period_label=v.period_label,
                                message=f"{v.metric_label} is negative ({v.value:,.0f}); check the sign convention."))
    return issues


def change_issues(changes: list[Change]) -> list[Issue]:
    return [Issue(severity="warning", code="concept_changed", metric_id=c.metric_id, period_label=c.current.period_label,
                  message=c.note) for c in changes if "Concept changed" in c.note]
