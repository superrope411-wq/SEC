"""How each metric is worded in Microsoft-style filing text, used both to find passages and to
check that a cited number is about the right metric (not a segment or product line)."""

from __future__ import annotations

# Lowercase phrases that name the metric itself. Order matters only for display.
METRIC_TERMS: dict[str, list[str]] = {
    "revenue": ["total revenue", "revenue"],
    "operating_income": ["operating income"],
    "net_income": ["net income"],
    "operating_cash_flow": ["cash from operations", "net cash from operations", "cash flows from operations",
                            "operating cash flow"],
    "capex": ["additions to property and equipment", "capital expenditures", "cash used for property and equipment"],
    "free_cash_flow": ["free cash flow"],
    "operating_margin": ["operating margin", "operating income as a percent"],
    "net_margin": ["net margin"],
    "cash": ["cash and cash equivalents", "cash, cash equivalents"],
    "accounts_receivable": ["accounts receivable"],
    "deferred_revenue_current": ["unearned revenue", "short-term unearned revenue"],
    "deferred_revenue_noncurrent": ["long-term unearned revenue", "unearned revenue"],
    "debt_current": ["current portion of long-term debt", "debt"],
    "debt_noncurrent": ["long-term debt", "debt"],
    "total_debt": ["debt"],
    "cash_conversion": ["cash from operations", "net income"],
}

# Extra words that tend to appear in passages that explain a metric's movement.
EXPLAIN_TERMS = ["increased", "decreased", "driven", "due to", "primarily", "offset", "growth", "decline",
                 "impact", "compared"]

# Words for things that are not in this app's metrics; a question about them cannot be answered
# from verified calculations even if the filing mentions them.
COMPANY_NAMES = {"MSFT": ["microsoft"], "CRM": ["salesforce"], "ADBE": ["adobe"]}

STOPWORDS = set("""a an and are as at be by did do does for from had has have how in is it its of on or
our that the their this to was were what when which why with would will vs versus than during compared
change changed changes microsoft msft company quarter year fiscal fy q1 q2 q3 q4 period""".split())
