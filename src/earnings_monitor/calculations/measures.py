"""Derived measures and period-over-period changes. Python computes every number here;
nothing in this module guesses or fills in missing data."""

from __future__ import annotations

from typing import Callable

from earnings_monitor.models import Change, MetricValue

# Definitions shown in the dashboard and exports.
MEASURE_DEFINITIONS = {
    "free_cash_flow": ("Free cash flow", "USD", "Operating cash flow − Capital expenditures"),
    "operating_margin": ("Operating margin", "ratio", "Operating income ÷ Revenue"),
    "net_margin": ("Net margin", "ratio", "Net income ÷ Revenue"),
    "cash_conversion": ("Cash-flow conversion", "ratio", "Operating cash flow ÷ Net income (denominator: net income)"),
    "total_debt": ("Total debt", "USD", "Current portion of long-term debt + Long-term debt"),
}


def derive(
    measure_id: str,
    inputs: dict[str, MetricValue],
    fn: Callable[..., float],  # called with the input values, in the order given
    denominator: str | None = None,
) -> MetricValue:
    label, unit, formula = MEASURE_DEFINITIONS[measure_id]
    first = next(iter(inputs.values()))
    common = dict(
        company=first.company, cik=first.cik, metric_id=measure_id, metric_label=label, unit=unit,
        period_type=first.period_type if unit == "USD" else "duration",
        basis=first.basis if unit == "USD" else "ratio",
        period_start=first.period_start, period_end=first.period_end, period_label=first.period_label,
        formula=formula,
    )
    if unit == "USD" and first.basis == "instant":
        common["period_type"] = "instant"
    missing = [n for n, v in inputs.items() if not v.is_available]
    if missing:
        return MetricValue(**common, value=None, status="missing",
                           notes=[f"Cannot compute: {', '.join(missing)} not available for {first.period_label}."],
                           selection_reason="Derived measure; an input is missing.")
    vals = {n: v.value for n, v in inputs.items()}
    sources = [s for v in inputs.values() for s in v.sources]
    restated = any(v.restated for v in inputs.values())
    if denominator is not None and vals[denominator] <= 0:
        return MetricValue(**common, value=None, status="not_meaningful", input_values=vals, sources=sources,
                           notes=[f"Not meaningful: {denominator} is {vals[denominator]:,.0f} (zero or negative)."],
                           selection_reason="Derived measure; denominator is zero or negative.", restated=restated)
    return MetricValue(**common, value=fn(*vals.values()),
                       status="derived", input_values=vals, sources=sources, restated=restated,
                       selection_reason=f"Calculated as {formula} from the selected values listed as inputs.")


def period_measures(v: dict[str, MetricValue]) -> dict[str, MetricValue]:
    """Measures for one period, given that period's metric values keyed by metric id."""
    out: dict[str, MetricValue] = {}
    out["free_cash_flow"] = derive(
        "free_cash_flow",
        {"Operating cash flow": v["operating_cash_flow"], "Capital expenditures": v["capex"]},
        lambda ocf, capex: ocf - capex,
    )
    out["operating_margin"] = derive(
        "operating_margin", {"Operating income": v["operating_income"], "Revenue": v["revenue"]},
        lambda oi, rev: oi / rev, denominator="Revenue",
    )
    out["net_margin"] = derive(
        "net_margin", {"Net income": v["net_income"], "Revenue": v["revenue"]},
        lambda ni, rev: ni / rev, denominator="Revenue",
    )
    out["cash_conversion"] = derive(
        "cash_conversion", {"Operating cash flow": v["operating_cash_flow"], "Net income": v["net_income"]},
        lambda ocf, ni: ocf / ni, denominator="Net income",
    )
    if "debt_current" in v and "debt_noncurrent" in v:
        out["total_debt"] = derive(
            "total_debt",
            {"Current portion of long-term debt": v["debt_current"], "Long-term debt": v["debt_noncurrent"]},
            lambda cur, lt: cur + lt,
        )
    return out


def compare(current: MetricValue, prior: MetricValue, comparison: str) -> Change:
    is_ratio = current.unit == "ratio"
    kind = "percentage_points" if is_ratio else "percent"
    if not (current.is_available and prior.is_available):
        which = "current" if not current.is_available else "prior"
        return Change(metric_id=current.metric_id, metric_label=current.metric_label, unit=current.unit,
                      comparison=comparison, current=current, prior=prior, abs_change=None, pct_change=None,
                      change_kind=kind, note=f"No change computed: {which} value unavailable.")
    if is_ratio:
        return Change(metric_id=current.metric_id, metric_label=current.metric_label, unit="ratio",
                      comparison=comparison, current=current, prior=prior,
                      abs_change=(current.value - prior.value) * 100, pct_change=None, change_kind=kind,
                      note="Change shown in percentage points.")
    diff = current.value - prior.value
    note = ""
    pct = None
    if prior.value > 0:
        pct = diff / prior.value
    else:
        note = f"Percent change not meaningful: prior value is {prior.value:,.0f}."
    if current.concept and prior.concept and current.concept != prior.concept:
        note = (note + " " if note else "") + f"Concept changed ({prior.concept} → {current.concept}); check comparability."
    return Change(metric_id=current.metric_id, metric_label=current.metric_label, unit=current.unit,
                  comparison=comparison, current=current, prior=prior, abs_change=diff, pct_change=pct,
                  change_kind=kind, note=note)
