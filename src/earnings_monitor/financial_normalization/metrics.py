"""Metric definitions: which XBRL concepts may represent each metric, in order of preference.

A concept appearing in this list is necessary but not sufficient for selection: selection.py
also checks taxonomy, unit, period type, exact period dates, form type and filing date, and
records the reason for every choice. See docs/FACT_SELECTION_POLICY.md.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Metric:
    id: str
    label: str
    period_type: str  # "duration" or "instant"
    concepts: tuple[str, ...]
    definition: str
    unit: str = "USD"
    taxonomy: str = "us-gaap"
    notes: str = ""
    cumulative_in_10q: bool = False  # cash-flow items are usually reported year-to-date


METRICS: dict[str, Metric] = {m.id: m for m in [
    Metric(
        "revenue", "Revenue", "duration",
        ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"),
        "Total consolidated revenue as reported on the income statement.",
        notes="Companies switched to RevenueFromContractWithCustomerExcludingAssessedTax around ASC 606 adoption (2018).",
    ),
    Metric(
        "operating_income", "Operating income", "duration", ("OperatingIncomeLoss",),
        "Consolidated operating income (loss). Negative values are losses.",
    ),
    Metric(
        "net_income", "Net income", "duration", ("NetIncomeLoss",),
        "Net income (loss) attributable to the parent company.",
    ),
    Metric(
        "operating_cash_flow", "Operating cash flow", "duration",
        ("NetCashProvidedByUsedInOperatingActivities",),
        "Net cash provided by (used in) operating activities.",
        cumulative_in_10q=True,
    ),
    Metric(
        "capex", "Capital expenditures", "duration",
        ("PaymentsToAcquirePropertyPlantAndEquipment",),
        "Cash paid for property and equipment, reported as a positive outflow.",
        notes="Excludes finance leases and acquisitions. Some companies use other concepts; missing is shown, not guessed.",
        cumulative_in_10q=True,
    ),
    Metric(
        "cash", "Cash and cash equivalents", "instant", ("CashAndCashEquivalentsAtCarryingValue",),
        "Cash and cash equivalents on the balance sheet. Excludes short-term investments.",
    ),
    Metric(
        "debt_current", "Current portion of long-term debt", "instant",
        ("LongTermDebtCurrent", "DebtCurrent"),
        "Debt due within 12 months as reported on the balance sheet.",
        notes="Commercial paper and other short-term borrowings are not included in milestone 1.",
    ),
    Metric(
        "debt_noncurrent", "Long-term debt", "instant",
        ("LongTermDebtNoncurrent",),
        "Long-term debt excluding the current portion.",
    ),
    Metric(
        "accounts_receivable", "Accounts receivable, net", "instant",
        ("AccountsReceivableNetCurrent",),
        "Current trade receivables net of allowances.",
    ),
    Metric(
        "deferred_revenue_current", "Deferred revenue (current)", "instant",
        ("ContractWithCustomerLiabilityCurrent", "DeferredRevenueCurrent"),
        "Current contract liabilities / unearned revenue.",
        notes="Comparable across companies only when both report contract liabilities on the same basis.",
    ),
    Metric(
        "deferred_revenue_noncurrent", "Deferred revenue (non-current)", "instant",
        ("ContractWithCustomerLiabilityNoncurrent", "DeferredRevenueNoncurrent"),
        "Non-current contract liabilities / unearned revenue.",
    ),
    # Used only for validation (balance-sheet identity), not displayed as a metric.
    Metric("assets", "Total assets", "instant", ("Assets",), "Total assets."),
    Metric(
        "liabilities_and_equity", "Total liabilities and equity", "instant",
        ("LiabilitiesAndStockholdersEquity",), "Total liabilities and stockholders' equity.",
    ),
]}

DISPLAY_METRICS = [
    "revenue", "operating_income", "net_income", "operating_cash_flow", "capex", "cash",
    "debt_current", "debt_noncurrent", "accounts_receivable",
    "deferred_revenue_current", "deferred_revenue_noncurrent",
]


# Company-specific concept lists. Each replaces the default list for one company and metric,
# and each was checked against that company's face balance sheet on EDGAR (the statement
# page names the XBRL concept on every line). A tag's official definition is not enough:
# the same concept can mean different things in different companies' filings.
COMPANY_CONCEPTS: dict[str, dict[str, tuple[tuple[str, ...], str]]] = {
    "ADBE": {
        "debt_current": (
            ("DebtCurrent", "LongTermDebtCurrent"),
            "Adobe tags the current 'Debt' line of its balance sheet with DebtCurrent (1,499M at "
            "2024-11-29 in the FY2025 10-K). It also reports LongTermDebtCurrent, 1,500M for the same "
            "date, which is not the balance-sheet line, so DebtCurrent is tried first.",
        ),
        "debt_noncurrent": (
            ("LongTermDebtNoncurrent", "LongTermDebt"),
            "Since FY2015 Adobe tags the non-current 'Debt' line of its balance sheet with LongTermDebt, "
            "whose us-gaap definition would include the current portion. On Adobe's balance sheets the "
            "current portion is a separate line (DebtCurrent), so LongTermDebt is accepted as the "
            "non-current amount for Adobe only. Other companies use LongTermDebt for total debt "
            "(Salesforce: 14,439M = 4,000M current + 10,439M non-current at 2026-01-31).",
        ),
    },
}


def metric_for(metric: Metric, ticker: str) -> Metric:
    """The metric with the company's concept list, if the company has an override."""
    override = COMPANY_CONCEPTS.get(ticker, {}).get(metric.id)
    if override is None:
        return metric
    concepts, why = override
    return replace(metric, concepts=concepts, notes=(metric.notes + " " if metric.notes else "") + why)


def concept_override_reason(metric_id: str, ticker: str) -> str | None:
    o = COMPANY_CONCEPTS.get(ticker, {}).get(metric_id)
    return o[1] if o else None
