"""Transparent, configurable rules that decide which changes are surfaced as findings.

A flag means "worth a closer look", never "good" or "bad". Each rule states its threshold so
the analyst can see exactly why something was flagged. Edit RULES to tune thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass

from earnings_monitor.models import Change, Finding


@dataclass(frozen=True)
class Rule:
    id: str
    metric_id: str
    threshold: float  # percent as a fraction, or percentage points
    priority: int
    description: str


RULES: list[Rule] = [
    Rule("revenue_change", "revenue", 0.10, 1, "Revenue changed by at least 10%"),
    Rule("operating_margin_shift", "operating_margin", 2.0, 1, "Operating margin moved by at least 2 percentage points"),
    Rule("net_margin_shift", "net_margin", 2.0, 2, "Net margin moved by at least 2 percentage points"),
    Rule("fcf_change", "free_cash_flow", 0.20, 2, "Free cash flow changed by at least 20%"),
    Rule("deferred_revenue_change", "deferred_revenue_current", 0.10, 2, "Current deferred revenue changed by at least 10%"),
    Rule("debt_change", "total_debt", 0.10, 2, "Total debt changed by at least 10%"),
    Rule("cash_change", "cash", 0.20, 3, "Cash and equivalents changed by at least 20%"),
]

# Receivables growing much faster than revenue can indicate collection or timing changes.
AR_VS_REVENUE_GAP_PP = 10.0
# Operating cash flow well below net income means earnings are not (yet) turning into cash.
CASH_CONVERSION_FLOOR = 0.8


def _fmt_pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def evaluate(changes: dict[str, Change], comparison: str) -> list[Finding]:
    findings: list[Finding] = []
    for rule in RULES:
        ch = changes.get(rule.metric_id)
        if ch is None or ch.abs_change is None:
            continue
        if ch.change_kind == "percentage_points":
            if abs(ch.abs_change) >= rule.threshold:
                direction = "rose" if ch.abs_change > 0 else "fell"
                findings.append(Finding(
                    rule_id=rule.id, priority=rule.priority, metric_ids=[rule.metric_id],
                    title=f"{ch.metric_label} {direction} {abs(ch.abs_change):.1f} pp ({comparison.lower()})",
                    why=f"Rule: {rule.description}. {ch.prior.period_label}: {ch.prior.value * 100:.1f}% → "
                        f"{ch.current.period_label}: {ch.current.value * 100:.1f}%.",
                ))
        elif ch.pct_change is not None and abs(ch.pct_change) >= rule.threshold:
            direction = "increased" if ch.pct_change > 0 else "decreased"
            findings.append(Finding(
                rule_id=rule.id, priority=rule.priority, metric_ids=[rule.metric_id],
                title=f"{ch.metric_label} {direction} {_fmt_pct(ch.pct_change)} ({comparison.lower()})",
                why=f"Rule: {rule.description}. {ch.prior.period_label}: {ch.prior.value:,.0f} → "
                    f"{ch.current.period_label}: {ch.current.value:,.0f} {ch.unit}.",
            ))

    ar, rev = changes.get("accounts_receivable"), changes.get("revenue")
    if ar and rev and ar.pct_change is not None and rev.pct_change is not None:
        gap = (ar.pct_change - rev.pct_change) * 100
        if gap >= AR_VS_REVENUE_GAP_PP:
            findings.append(Finding(
                rule_id="ar_outpacing_revenue", priority=1, metric_ids=["accounts_receivable", "revenue"],
                title=f"Receivables grew {gap:.1f} pp faster than revenue ({comparison.lower()})",
                why=f"Rule: receivables growth exceeds revenue growth by at least {AR_VS_REVENUE_GAP_PP:.0f} pp. "
                    f"Receivables {_fmt_pct(ar.pct_change)}, revenue {_fmt_pct(rev.pct_change)}. "
                    "Note receivables are a point-in-time balance and revenue is a period flow.",
            ))

    cc = changes.get("cash_conversion")
    if cc and cc.current.is_available and cc.current.value < CASH_CONVERSION_FLOOR:
        findings.append(Finding(
            rule_id="low_cash_conversion", priority=2, metric_ids=["cash_conversion"],
            title=f"Operating cash flow was {cc.current.value:.2f}× net income in {cc.current.period_label}",
            why=f"Rule: cash-flow conversion (operating cash flow ÷ net income) below {CASH_CONVERSION_FLOOR}. "
                "Quarterly cash flow is seasonal for many companies; compare with the same quarter last year.",
        ))
    return sorted(findings, key=lambda f: f.priority)
