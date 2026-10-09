"""SYNTHETIC test data. Not real financial data and never shown in the app.

Builds a companyfacts-shaped document for a fictional company with a June 30 fiscal year
end, so tests can exercise period logic with known answers:
- 10-Qs report 3-month income facts but only year-to-date cash flow facts.
- 10-Ks report full-year facts only (no Q4), so Q4 must be derived.
- Revenue for FY2025 Q1 is restated (100,000 → 102,000) in the FY2026 Q1 10-Q.
- One fact is duplicated within a filing (same value, with and without a frame).
"""

from __future__ import annotations

from datetime import date, timedelta

CIK = 999999
FY_STARTS = {2023: date(2022, 7, 1), 2024: date(2023, 7, 1), 2025: date(2024, 7, 1), 2026: date(2025, 7, 1)}
Q_ENDS = {
    2023: [date(2022, 9, 30), date(2022, 12, 31), date(2023, 3, 31), date(2023, 6, 30)],
    2024: [date(2023, 9, 30), date(2023, 12, 31), date(2024, 3, 31), date(2024, 6, 30)],
    2025: [date(2024, 9, 30), date(2024, 12, 31), date(2025, 3, 31), date(2025, 6, 30)],
    2026: [date(2025, 9, 30)],
}
# Standalone quarterly values (the "truth" tests check against).
REVENUE = {2023: [80_000, 82_000, 84_000, 90_000], 2024: [90_000, 92_000, 95_000, 99_000],
           2025: [100_000, 104_000, 108_000, 112_000], 2026: [120_000]}
OP_INCOME = {y: [round(v * 0.4) for v in vals] for y, vals in REVENUE.items()}
NET_INCOME = {y: [round(v * 0.3) for v in vals] for y, vals in REVENUE.items()}
OCF = {2023: [30_000, 20_000, 35_000, 40_000], 2024: [33_000, 22_000, 38_000, 44_000],
       2025: [36_000, 25_000, 41_000, 47_000], 2026: [45_000]}
CAPEX = {y: [5_000 + 1_000 * i for i in range(len(v))] for y, v in REVENUE.items()}
CASH = {(y, i): 50_000 + 1_000 * (4 * (y - 2023) + i) for y in Q_ENDS for i in range(len(Q_ENDS[y]))}
AR = {(y, i): 40_000 + 500 * (4 * (y - 2023) + i) for y in Q_ENDS for i in range(len(Q_ENDS[y]))}
ASSETS = {(y, i): 500_000 + 10_000 * (4 * (y - 2023) + i) for y in Q_ENDS for i in range(len(Q_ENDS[y]))}

RESTATED_FY2025_Q1_REVENUE = 102_000


def _q_start(y, i):
    return FY_STARTS[y] if i == 0 else Q_ENDS[y][i - 1] + timedelta(days=1)


def build() -> tuple[dict, dict]:
    facts: dict[str, list] = {}
    filings = []
    seq = 0

    def add(concept, start, end, val, accn, form, filed, fy, fp, frame=None):
        f = {"end": end.isoformat(), "val": val, "accn": accn, "fy": fy, "fp": fp, "form": form, "filed": filed.isoformat()}
        if start:
            f["start"] = start.isoformat()
        if frame:
            f["frame"] = frame
        facts.setdefault(concept, []).append(f)

    for y in sorted(Q_ENDS):
        for i, qend in enumerate(Q_ENDS[y]):
            seq += 1
            is_k = i == 3
            form = "10-K" if is_k else "10-Q"
            filed = qend + timedelta(days=30 if is_k else 25)
            accn = f"0000{CIK}-{filed.year % 100:02d}-{seq:06d}"
            fp = "FY" if is_k else f"Q{i + 1}"
            filings.append((accn, form, filed, qend))
            years = [y, y - 1] if (y - 1) in Q_ENDS else [y]
            if is_k:
                for yy in [y, y - 1, y - 2]:
                    if yy not in Q_ENDS or len(Q_ENDS[yy]) < 4:
                        continue
                    for c, d in [("RevenueFromContractWithCustomerExcludingAssessedTax", REVENUE), ("OperatingIncomeLoss", OP_INCOME),
                                 ("NetIncomeLoss", NET_INCOME), ("NetCashProvidedByUsedInOperatingActivities", OCF),
                                 ("PaymentsToAcquirePropertyPlantAndEquipment", CAPEX)]:
                        add(c, FY_STARTS[yy], Q_ENDS[yy][3], sum(d[yy]), accn, form, filed, y, fp)
            else:
                for yy in years:
                    s, e = _q_start(yy, i), Q_ENDS[yy][i]
                    rev = REVENUE[yy][i]
                    if yy == 2025 and i == 0 and y == 2026:
                        rev = RESTATED_FY2025_Q1_REVENUE
                    add("RevenueFromContractWithCustomerExcludingAssessedTax", s, e, rev, accn, form, filed, y, fp)
                    add("OperatingIncomeLoss", s, e, OP_INCOME[yy][i], accn, form, filed, y, fp)
                    add("NetIncomeLoss", s, e, NET_INCOME[yy][i], accn, form, filed, y, fp)
                    # Cash flow: year-to-date only.
                    add("NetCashProvidedByUsedInOperatingActivities", FY_STARTS[yy], e, sum(OCF[yy][: i + 1]), accn, form, filed, y, fp)
                    add("PaymentsToAcquirePropertyPlantAndEquipment", FY_STARTS[yy], e, sum(CAPEX[yy][: i + 1]), accn, form, filed, y, fp)
                    if i > 0:  # YTD income facts too, like real 10-Qs
                        add("RevenueFromContractWithCustomerExcludingAssessedTax", FY_STARTS[yy], e,
                            sum(REVENUE[yy][: i + 1]), accn, form, filed, y, fp)
                        add("OperatingIncomeLoss", FY_STARTS[yy], e, sum(OP_INCOME[yy][: i + 1]), accn, form, filed, y, fp)
                        add("NetIncomeLoss", FY_STARTS[yy], e, sum(NET_INCOME[yy][: i + 1]), accn, form, filed, y, fp)
            # Balance sheet: current period end and prior fiscal year end.
            inst = [(y, i)]
            if (y - 1) in Q_ENDS:
                inst.append((y - 1, 3))
            for yy, ii in inst:
                e = Q_ENDS[yy][ii]
                add("CashAndCashEquivalentsAtCarryingValue", None, e, CASH[(yy, ii)], accn, form, filed, y, fp)
                add("AccountsReceivableNetCurrent", None, e, AR[(yy, ii)], accn, form, filed, y, fp)
                add("Assets", None, e, ASSETS[(yy, ii)], accn, form, filed, y, fp)
                add("LiabilitiesAndStockholdersEquity", None, e, ASSETS[(yy, ii)], accn, form, filed, y, fp)

    # Exact duplicate inside one filing (as companyfacts does with frames).
    dup = dict(facts["NetIncomeLoss"][0])
    dup["frame"] = "CY2022Q3"
    facts["NetIncomeLoss"].append(dup)

    companyfacts = {
        "cik": CIK, "entityName": "SYNTHETIC TEST CO (NOT REAL)",
        "facts": {"us-gaap": {c: {"label": c, "units": {"USD": v}} for c, v in facts.items()}},
    }
    submissions = {
        "cik": str(CIK), "name": "SYNTHETIC TEST CO (NOT REAL)", "fiscalYearEnd": "0630",
        "filings": {"recent": {
            "accessionNumber": [a for a, *_ in filings], "form": [f for _, f, *_ in filings],
            "filingDate": [d.isoformat() for _, _, d, _ in filings],
            "reportDate": [r.isoformat() for *_, r in filings],
            "primaryDocument": [f"doc{i}.htm" for i in range(len(filings))],
        }},
    }
    return companyfacts, submissions


def accn_for(form_period_end: date) -> str:
    _, subs = build()
    r = subs["filings"]["recent"]
    for a, rd in zip(r["accessionNumber"], r["reportDate"]):
        if rd == form_period_end.isoformat():
            return a
    raise KeyError(form_period_end)
