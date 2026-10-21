"""The fiscal year under test for each company, and where each metric sits on its statements.

Line items are chosen by their printed label on the face statements (read by a person from
the EDGAR statement pages), not by XBRL concept, so the reference does not inherit the
pipeline's concept choices. The concept printed on each line is recorded alongside, which is
how company-specific tagging (e.g. Adobe's LongTermDebt) was found.

A label spec is (statement, label or regex, region). Region limits the search to rows between
two other rows, for labels that repeat (Adobe prints "Debt" and "Deferred revenue" under both
current and non-current liabilities).
"""

from __future__ import annotations

import re

CURRENT = (re.compile(r"^Current liabilities"), re.compile(r"^Total current liabilities"))
NONCURRENT = (re.compile(r"^Total current liabilities"), re.compile(r"^Total liabilities$"))

COMPANIES = {
    "CRM": {
        "cik": 1108524,
        "name": "Salesforce",
        "fiscal_year": "FY2026 (Feb 1, 2025 to Jan 31, 2026)",
        # Filings of the fiscal year under test, in filing order: (accession, form, filed, label)
        "filings": [
            ("0001108524-25-000030", "10-Q", "2025-05-29", "10-Q FY2026 Q1"),
            ("0001108524-25-000088", "10-Q", "2025-09-04", "10-Q FY2026 Q2"),
            ("0001108524-25-000238", "10-Q", "2025-12-04", "10-Q FY2026 Q3"),
            ("0001108524-26-000060", "10-K", "2026-03-02", "10-K FY2026"),
        ],
        # Prior-year filings: the figures that comparisons of the year under test display as
        # of an earlier date (e.g. the prior Q4, derived from the prior 10-K and Q3 10-Q).
        "prior_filings": [
            ("0001108524-24-000009", "10-Q", "2024-05-30", "10-Q FY2025 Q1"),
            ("0001108524-24-000022", "10-Q", "2024-08-29", "10-Q FY2025 Q2"),
            ("0001108524-24-000034", "10-Q", "2024-12-04", "10-Q FY2025 Q3"),
            ("0001108524-25-000006", "10-K", "2025-03-05", "10-K FY2025"),
        ],
        "labels": {
            "revenue": ("income", "Total revenues", None),
            "operating_income": ("income", "Income from operations", None),
            "net_income": ("income", "Net income", None),
            "operating_cash_flow": ("cashflow", "Net cash provided by operating activities", None),
            "capex": ("cashflow", "Capital expenditures", None),
            "cash": ("balance", "Cash and cash equivalents", None),
            "accounts_receivable": ("balance", "Accounts receivable, net", None),
            "deferred_revenue_current": ("balance", "Unearned revenue", None),
            "debt_current": ("balance", "Debt, current", None),
            "debt_noncurrent": ("balance", "Noncurrent debt", None),
            "assets": ("balance", "Total assets", None),
            "liabilities_and_equity": ("balance", re.compile(r"^Total liabilities and stockholders. equity$"), None),
        },
    },
    "ADBE": {
        "cik": 796343,
        "name": "Adobe",
        "fiscal_year": "FY2025 (Nov 30, 2024 to Nov 28, 2025, 52 weeks)",
        "filings": [
            ("0000796343-25-000059", "10-Q", "2025-03-26", "10-Q FY2025 Q1"),
            ("0000796343-25-000073", "10-Q", "2025-06-25", "10-Q FY2025 Q2"),
            ("0000796343-25-000107", "10-Q", "2025-09-24", "10-Q FY2025 Q3"),
            ("0000796343-26-000003", "10-K", "2026-01-15", "10-K FY2025"),
        ],
        "prior_filings": [
            ("0000796343-24-000065", "10-Q", "2024-03-27", "10-Q FY2024 Q1"),
            ("0000796343-24-000150", "10-Q", "2024-06-26", "10-Q FY2024 Q2"),
            ("0000796343-24-000208", "10-Q", "2024-09-25", "10-Q FY2024 Q3"),
            ("0000796343-25-000004", "10-K", "2025-01-13", "10-K FY2024"),
        ],
        "labels": {
            "revenue": ("income", re.compile(r"^(Total revenue|Revenue)$"), None),
            "operating_income": ("income", "Operating income", None),
            "net_income": ("income", "Net income", None),
            "operating_cash_flow": ("cashflow", "Net cash provided by operating activities", None),
            "capex": ("cashflow", "Purchases of property and equipment", None),
            "cash": ("balance", "Cash and cash equivalents", None),
            "accounts_receivable": ("balance", re.compile(r"^Trade receivables, net"), None),
            "deferred_revenue_current": ("balance", "Deferred revenue", CURRENT),
            "deferred_revenue_noncurrent": ("balance", "Deferred revenue", NONCURRENT),
            "debt_current": ("balance", "Debt", CURRENT),
            "debt_noncurrent": ("balance", "Debt", NONCURRENT),
            "assets": ("balance", "Total assets", None),
            "liabilities_and_equity": ("balance", re.compile(r"^Total liabilities and stockholders. equity$"), None),
        },
    },
}
