"""Reconcile the pipeline against an independently built reference dataset for Microsoft FY2025.

Reference: evaluation/msft_fy2025_reference.csv, typed from the statement pages (R2/R4/R6)
of the four FY2025 filings on EDGAR, in millions of USD as printed. Nothing in that file
was produced by the pipeline.

Actual: the pipeline run in fixture mode on the unmodified SEC responses under
tests/fixtures/real (downloaded by .github/workflows/fetch-sec-data.yml; see manifest.json).

Tolerances (explicit):
  USD values   : |actual - expected| <= 500,000.  Statements print millions; XBRL facts are in
                 whole dollars, so anything within half a million is the same number rounded.
  Ratios       : |actual - expected| <= 0.0001 (0.01 percentage point); expected ratios are
                 computed here from the reference figures in millions.
A missing or not-meaningful actual value never passes. Line items the pipeline does not
cover (short-term debt) are listed as NOT COVERED and excluded from the pass count.

Usage: python evaluation/reconcile_msft_fy2025.py
Writes evaluation/MSFT_FY2025_reconciliation.xlsx and .md
"""

from __future__ import annotations

import csv
import os
import sys
from collections import OrderedDict
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("EM_MODE", "fixture")
os.environ.setdefault("EM_FIXTURE_DIR", str(ROOT / "tests" / "fixtures" / "real"))
os.environ.setdefault("EM_DATA_DIR", str(ROOT / "data" / "verification"))

from earnings_monitor.analysis import analyze, available_comparisons  # noqa: E402
from earnings_monitor.config import COMPANIES, load_settings  # noqa: E402
from earnings_monitor.exports.tables import changes_frame, values_frame  # noqa: E402
from earnings_monitor.financial_normalization.metrics import METRICS  # noqa: E402
from earnings_monitor.financial_normalization.selection import FactSelector  # noqa: E402
from earnings_monitor.pipeline import load_company  # noqa: E402

USD_TOL = 500_000.0
RATIO_TOL = 1e-4
REF = ROOT / "evaluation" / "msft_fy2025_reference.csv"
OUT_XLSX = ROOT / "evaluation" / "MSFT_FY2025_reconciliation.xlsx"
OUT_MD = ROOT / "evaluation" / "MSFT_FY2025_reconciliation.md"

FILINGS = OrderedDict([  # the fiscal year under test: accn -> (label, filed); each is analyzed as of its filing date
    ("0000950170-24-118967", ("10-Q FY2025 Q1", date(2024, 10, 30))),
    ("0000950170-25-010491", ("10-Q FY2025 Q2", date(2025, 1, 29))),
    ("0000950170-25-061046", ("10-Q FY2025 Q3", date(2025, 4, 30))),
    ("0000950170-25-100235", ("10-K FY2025", date(2025, 7, 30))),
])
# Prior-year 10-Qs: only their balance sheets are in the reference, for the prior-period
# instants that FY2025 year-over-year comparisons display.
REFERENCE_FILINGS = OrderedDict(FILINGS)
REFERENCE_FILINGS.update([
    ("0000950170-23-054855", ("10-Q FY2024 Q1", date(2023, 10, 24))),
    ("0000950170-24-008814", ("10-Q FY2024 Q2", date(2024, 1, 30))),
    ("0000950170-24-048288", ("10-Q FY2024 Q3", date(2024, 4, 25))),
])


def d(s: str) -> date | None:
    return date.fromisoformat(s) if s else None


def load_reference() -> list[dict]:
    rows = list(csv.DictReader(REF.open()))
    for r in rows:
        r["period_start"] = d(r["period_start"])
        r["period_end"] = d(r["period_end"])
        r["filed"] = d(r["filed"])
        r["value_musd"] = float(r["value_musd"])
    return rows


def ref_value(rows, metric_id, start, end, accn=None) -> float | None:
    for r in rows:
        if r["metric_id"] == metric_id and r["period_start"] == start and r["period_end"] == end \
                and (accn is None or r["accn"] == accn):
            return r["value_musd"]
    return None


def main() -> int:
    settings = load_settings()
    data, stats = load_company(COMPANIES["MSFT"], settings)
    manifest = ROOT / "tests" / "fixtures" / "real" / "manifest.json"
    print(f"Loaded {stats['observations']:,} observations from {data.data_source} "
          f"(raw sha256 {data.raw_sha256[:12]}…), {stats['filings']} filings, calendar: "
          f"{[q.label for q in data.calendar.quarters[-6:]]}")
    ref = load_reference()

    # ---- actual values from the pipeline, per filing (as-of its filing date) -----------------
    analyses: dict[str, dict] = {}
    for accn, (label, filed) in FILINGS.items():
        analyses[accn] = {}
        for comp in available_comparisons(data, accn):
            a = analyze(data, accn, comp)
            assert a.as_of == filed, (a.as_of, filed)
            analyses[accn][comp] = a

    def actual_value(accn: str, metric_id: str, start, end, basis_hint: str | None = None):
        """A displayed value for this period from any analysis of the given filing."""
        for comp, a in analyses[accn].items():
            for v in a.all_values:
                if v.metric_id == metric_id and v.period_start == start and v.period_end == end:
                    if basis_hint and v.basis != basis_hint:
                        continue
                    return v
        return None

    def selector(accn: str) -> FactSelector:
        return FactSelector(data.obs, data.company, REFERENCE_FILINGS[accn][1], data.primary_documents())

    records: list[dict] = []
    provenance: list[dict] = []

    def record(section, accn, metric_id, label, period, expected_musd, v, kind="USD", expected_note=""):
        filed = REFERENCE_FILINGS[accn][1]
        if v is None:
            status, actual, diff, src, note = "FAIL", None, None, "", "pipeline produced no value for this period"
        elif not v.is_available:
            status, actual, diff = "FAIL", None, None
            src, note = "", f"pipeline status={v.status}: " + " ".join(v.notes)
        else:
            if kind == "USD":
                expected = expected_musd * 1e6
                diff = v.value - expected
                ok = abs(diff) <= USD_TOL
            else:
                expected = expected_musd
                diff = v.value - expected
                ok = abs(diff) <= RATIO_TOL
            actual = v.value
            status = "PASS" if ok else "FAIL"
            src = "; ".join(f"{s.form} {s.accn} filed {s.filed} {s.concept} {s.period_start or ''}..{s.period_end}={s.value:,.0f}"
                            for s in v.sources)
            late = [s for s in v.sources if s.filed > filed]
            note = ("AVAILABILITY VIOLATION: source filed after as-of date. " if late else "") + \
                   (f"derived: {v.formula}; inputs {v.input_values}" if v.status == "derived" else "") + \
                   (" RESTATED" if v.restated else "")
            if late:
                status = "FAIL"
            for s in v.sources:
                provenance.append({"Analysis of filing": REFERENCE_FILINGS[accn][0], "As-of (filing date)": filed, "Metric": label,
                                   "Period": period, "Value status": v.status, "Source form": s.form,
                                   "Source accession": s.accn, "Source filed": s.filed,
                                   "Available by as-of?": "yes" if s.filed <= filed else "NO",
                                   "XBRL concept": s.concept, "Source period": f"{s.period_start or ''}..{s.period_end}",
                                   "Source value (USD)": s.value, "Source URL": s.url})
        records.append({"Section": section, "Analysis of filing": REFERENCE_FILINGS[accn][0], "As-of (filing date)": filed,
                        "Metric": label, "Period": period,
                        "Expected (USD, from statement)" if kind == "USD" else "Expected (ratio)":
                            expected_musd * 1e6 if kind == "USD" else expected_musd,
                        "Actual (pipeline)": actual, "Difference": diff,
                        "Tolerance": USD_TOL if kind == "USD" else RATIO_TOL, "Status": status,
                        "Expected source": expected_note, "Actual sources": src, "Note": note,
                        "Metric ID": metric_id, "_accn": accn,
                        "_start": v.period_start if v is not None else None, "_end": v.period_end if v is not None else None})

    def pretty(start, end):
        return f"{start}..{end}" if start else f"at {end}"

    # ---- 1. Reported line items: every reference row ----------------------------------------
    for r in ref:
        m = r["metric_id"]
        period = pretty(r["period_start"], r["period_end"])
        if m == "short_term_debt":
            records.append({"Section": "Reported", "Analysis of filing": REFERENCE_FILINGS[r["accn"]][0], "As-of (filing date)": r["filed"],
                            "Metric": r["line_item"], "Period": period, "Expected (USD, from statement)": r["value_musd"] * 1e6,
                            "Actual (pipeline)": None, "Difference": None, "Tolerance": USD_TOL, "Status": "NOT COVERED",
                            "Expected source": r["source_url"], "Actual sources": "",
                            "Note": "Short-term debt / commercial paper is outside milestone 1 metrics (docs/LIMITATIONS.md)."})
            continue
        sel = selector(r["accn"])
        metric = METRICS[m]
        if metric.period_type == "instant":
            v = sel.instant_value(metric, r["period_end"], period)
        else:
            direct, notes = sel.select_exact(metric, r["period_start"], r["period_end"])
            v = sel._value(metric, "quarter", r["period_start"], r["period_end"], period, direct, notes)
        record("Reported", r["accn"], m, r["line_item"], period, r["value_musd"], v, expected_note=r["source_url"])

    # ---- 2. Derived standalone quarters and Q4 ------------------------------------------------
    def expect_q4(fy_accn, fy_start, q3_end, fy_end, m, nine_accn):
        fy = ref_value(ref, m, fy_start, fy_end, fy_accn)
        nine = ref_value(ref, m, fy_start, q3_end, nine_accn)
        return None if fy is None or nine is None else fy - nine

    k = "0000950170-25-100235"
    q3 = "0000950170-25-061046"
    for m, label in [("revenue", "Revenue"), ("operating_income", "Operating income"), ("net_income", "Net income"),
                     ("operating_cash_flow", "Net cash from operations"), ("capex", "Additions to property and equipment")]:
        exp = expect_q4(k, date(2024, 7, 1), date(2025, 3, 31), date(2025, 6, 30), m, q3)
        v = actual_value(k, m, date(2025, 4, 1), date(2025, 6, 30), "quarter")
        record("Derived Q4", k, m, label, "2025-04-01..2025-06-30 (FY2025 Q4 = FY − 9M)", exp, v,
               expected_note="FY2025 10-K R2/R6 minus FY2025 Q3 10-Q R2/R6 nine-month column")
        exp = expect_q4(k, date(2023, 7, 1), date(2024, 3, 31), date(2024, 6, 30), m, q3)
        v = actual_value(k, m, date(2024, 4, 1), date(2024, 6, 30), "quarter")
        record("Derived Q4", k, m, label, "2024-04-01..2024-06-30 (FY2024 Q4 = FY − 9M)", exp, v,
               expected_note="FY2025 10-K prior-year column minus FY2025 Q3 10-Q prior-year nine-month column")

    # Standalone Q2/Q3 as displayed (should equal the 3-month column; check against YTD difference too)
    for accn, qs, qe, ys in [("0000950170-25-010491", date(2024, 10, 1), date(2024, 12, 31), date(2024, 7, 1)),
                             ("0000950170-25-061046", date(2025, 1, 1), date(2025, 3, 31), date(2024, 7, 1))]:
        prev_end = qs.replace(day=1) - pd.Timedelta(days=1)
        prev_end = prev_end.date() if hasattr(prev_end, "date") else prev_end
        for m, label in [("revenue", "Revenue"), ("operating_income", "Operating income"), ("net_income", "Net income"),
                         ("operating_cash_flow", "Net cash from operations"), ("capex", "Additions to property and equipment")]:
            three = ref_value(ref, m, qs, qe, accn)
            ytd_now = ref_value(ref, m, ys, qe, accn)
            ytd_prev = ref_value(ref, m, ys, prev_end)  # from the previous 10-Q (6M) or Q1 10-Q (3M = YTD)
            cross = None if ytd_now is None or ytd_prev is None else ytd_now - ytd_prev
            v = actual_value(accn, m, qs, qe, "quarter")
            note = f"3-month column {three:,.0f}M; YTD difference {cross:,.0f}M" if cross is not None else "3-month column"
            if cross is not None and abs(cross - three) > 0.5:
                note += "  <-- reference inconsistency, check the statements"
            record("Displayed quarter", accn, m, label, pretty(qs, qe), three, v, expected_note=note)

    # ---- 3. Derived measures: FCF, margins, total debt ---------------------------------------
    def derived_checks(accn, start, end, basis):
        rev = ref_value(ref, "revenue", start, end)
        oi = ref_value(ref, "operating_income", start, end)
        ni = ref_value(ref, "net_income", start, end)
        ocf = ref_value(ref, "operating_cash_flow", start, end)
        capex = ref_value(ref, "capex", start, end)
        if None in (rev, oi, ni, ocf, capex):
            # Q4: build from FY − 9M
            fy_s = date(2024, 7, 1) if end == date(2025, 6, 30) else date(2023, 7, 1)
            q3e = date(2025, 3, 31) if end == date(2025, 6, 30) else date(2024, 3, 31)
            rev = expect_q4(k, fy_s, q3e, end, "revenue", q3); oi = expect_q4(k, fy_s, q3e, end, "operating_income", q3)
            ni = expect_q4(k, fy_s, q3e, end, "net_income", q3); ocf = expect_q4(k, fy_s, q3e, end, "operating_cash_flow", q3)
            capex = expect_q4(k, fy_s, q3e, end, "capex", q3)
        period = pretty(start, end)
        record("Derived measure", accn, "free_cash_flow", "Free cash flow (OCF − capex)", period, ocf - capex,
               actual_value(accn, "free_cash_flow", start, end, basis), expected_note=f"{ocf:,.0f} − {capex:,.0f} (millions)")
        record("Derived measure", accn, "operating_margin", "Operating margin (OI ÷ revenue)", period, oi / rev,
               actual_value(accn, "operating_margin", start, end), kind="ratio", expected_note=f"{oi:,.0f} ÷ {rev:,.0f}")
        record("Derived measure", accn, "net_margin", "Net margin (NI ÷ revenue)", period, ni / rev,
               actual_value(accn, "net_margin", start, end), kind="ratio", expected_note=f"{ni:,.0f} ÷ {rev:,.0f}")
        record("Derived measure", accn, "cash_conversion", "Cash conversion (OCF ÷ NI)", period, ocf / ni,
               actual_value(accn, "cash_conversion", start, end), kind="ratio", expected_note=f"{ocf:,.0f} ÷ {ni:,.0f}")

    derived_checks("0000950170-24-118967", date(2024, 7, 1), date(2024, 9, 30), "quarter")
    derived_checks("0000950170-25-010491", date(2024, 10, 1), date(2024, 12, 31), "quarter")
    derived_checks("0000950170-25-061046", date(2025, 1, 1), date(2025, 3, 31), "quarter")
    derived_checks(k, date(2025, 4, 1), date(2025, 6, 30), "quarter")
    derived_checks(k, date(2024, 7, 1), date(2025, 6, 30), "annual")
    derived_checks(k, date(2023, 7, 1), date(2024, 6, 30), "annual")
    for accn, end in [("0000950170-24-118967", date(2024, 9, 30)), ("0000950170-25-010491", date(2024, 12, 31)),
                      ("0000950170-25-061046", date(2025, 3, 31)), (k, date(2025, 6, 30)), (k, date(2024, 6, 30))]:
        cur = ref_value(ref, "debt_current", None, end, accn)
        lt = ref_value(ref, "debt_noncurrent", None, end, accn)
        record("Derived measure", accn, "total_debt", "Total debt (current LTD + long-term debt)", pretty(None, end), cur + lt,
               actual_value(accn, "total_debt", None, end), expected_note=f"{cur:,.0f} + {lt:,.0f} (millions)")

    # ---- 3b. Prior-year instants displayed by FY2025 year-over-year comparisons -------------
    for accn, prior_end in [("0000950170-24-118967", date(2023, 9, 30)), ("0000950170-25-010491", date(2023, 12, 31)),
                            ("0000950170-25-061046", date(2024, 3, 31)), (k, date(2024, 6, 30))]:
        for m in ["cash", "accounts_receivable", "debt_current", "debt_noncurrent",
                  "deferred_revenue_current", "deferred_revenue_noncurrent"]:
            exp = ref_value(ref, m, None, prior_end)
            if exp is None:
                continue
            record("Displayed prior instant", accn, m, METRICS[m].label, pretty(None, prior_end), exp,
                   actual_value(accn, m, None, prior_end), expected_note="prior-year 10-Q/10-K balance sheet")

    # ---- 4. Balance-sheet identity on reference figures (reference-internal check) ---------
    identity = []
    for r in ref:
        if r["metric_id"] == "assets":
            le = ref_value(ref, "liabilities_and_equity", None, r["period_end"], r["accn"])
            identity.append({"Filing": REFERENCE_FILINGS[r["accn"]][0], "Date": r["period_end"], "Total assets (M)": r["value_musd"],
                             "Liabilities + equity (M)": le, "Equal": r["value_musd"] == le})

    # ---- 5. Dashboard/export values equal the reconciled values -----------------------------
    # Every value that the export of each analysis shows for a reconciled metric and period must
    # equal the reconciled (PASS) value, matched by metric id and exact period dates.
    passed = {(rec["_accn"], rec["Metric ID"], rec["_start"], rec["_end"]): rec
              for rec in records if rec["Status"] == "PASS"}
    export_rows = []
    for accn, comps in analyses.items():
        for comp, a in comps.items():
            vf = values_frame(a)
            cf = changes_frame(a)
            for row in vf.to_dict("records"):
                start = row["Period start"] if pd.notna(row["Period start"]) else None
                rec = passed.get((accn, row["Metric ID"], start, row["Period end"]))
                if rec is None:
                    continue
                side = "Current" if row["Period"] == a.current_label else "Prior"
                change_val = cf.loc[cf["Metric ID"] == row["Metric ID"], f"{side} value"]
                exported = row["Value"]
                export_rows.append({"Filing": FILINGS[accn][0], "Comparison": comp, "Metric": row["Metric"],
                                    "Metric ID": row["Metric ID"], "Period": row["Period"], "Reconciled value": rec["Actual (pipeline)"],
                                    "Export 'Values and sources' value": exported,
                                    "Export 'Changes' value": change_val.iloc[0] if len(change_val) else None,
                                    "Sources in export": row["Sources"],
                                    "Equal": pd.notna(exported) and exported == rec["Actual (pipeline)"]
                                    and len(change_val) == 1 and change_val.iloc[0] == exported
                                    and bool(row["Sources"])})

    # ---- write ------------------------------------------------------------------------------
    df = pd.DataFrame(records).drop(columns=["_accn", "_start", "_end"])
    prov = pd.DataFrame(provenance)
    counted = df[df["Status"] != "NOT COVERED"]
    summary = pd.DataFrame([
        ("Reference rows (independently read)", len(ref)),
        ("Comparisons made", len(counted)),
        ("PASS", int((counted["Status"] == "PASS").sum())),
        ("FAIL", int((counted["Status"] == "FAIL").sum())),
        ("NOT COVERED (documented limitation)", int((df["Status"] == "NOT COVERED").sum())),
        ("Provenance rows checked", len(prov)),
        ("Sources filed after as-of date", int((prov["Available by as-of?"] == "NO").sum()) if len(prov) else 0),
        ("Exported values checked against reconciled values", len(export_rows)),
        ("Exported values that differ or lack sources", sum(not r["Equal"] for r in export_rows)),
        ("USD tolerance", USD_TOL), ("Ratio tolerance", RATIO_TOL),
        ("Pipeline data source", data.data_source), ("Raw companyfacts SHA-256", data.raw_sha256),
        ("Fixture manifest", str(manifest.relative_to(ROOT))),
    ], columns=["Item", "Value"])
    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as xw:
        summary.to_excel(xw, sheet_name="Summary", index=False)
        df.to_excel(xw, sheet_name="Reconciliation", index=False)
        prov.to_excel(xw, sheet_name="Provenance", index=False)
        pd.DataFrame(identity).to_excel(xw, sheet_name="Reference checks", index=False)
        pd.DataFrame(export_rows).to_excel(xw, sheet_name="Export match", index=False)
        pd.read_csv(REF).to_excel(xw, sheet_name="Reference dataset", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(max(10, max(len(str(c.value or "")) for c in col[:40]) + 2), 60)
            ws.freeze_panes = "A2"

    md = ["| Section | Filing | Metric | Period | Expected | Actual | Diff | Status |", "|---|---|---|---|---|---|---|---|"]
    for rec in records:
        exp = rec.get("Expected (USD, from statement)", rec.get("Expected (ratio)"))
        is_ratio = "Expected (ratio)" in rec
        f = (lambda x: "—" if x is None else (f"{x:.4f}" if is_ratio else f"{x:,.0f}"))
        md.append(f"| {rec['Section']} | {rec['Analysis of filing']} | {rec['Metric']} | {rec['Period']} | {f(exp)} | "
                  f"{f(rec['Actual (pipeline)'])} | {f(rec['Difference'])} | {rec['Status']} |")
    OUT_MD.write_text("\n".join(md) + "\n")
    print(summary.to_string(index=False))
    fails = df[df["Status"] == "FAIL"]
    if len(fails):
        print("\nFAILURES:")
        print(fails[["Analysis of filing", "Metric", "Period", "Expected (USD, from statement)", "Actual (pipeline)", "Note"]].to_string(index=False))
    print(f"\nwrote {OUT_XLSX}\nwrote {OUT_MD}")
    bad_exports = [r for r in export_rows if not r["Equal"]]
    if bad_exports:
        print("\nEXPORT MISMATCHES:")
        print(pd.DataFrame(bad_exports).to_string(index=False))
    return 0 if len(fails) == 0 and not bad_exports else 1


if __name__ == "__main__":
    sys.exit(main())
