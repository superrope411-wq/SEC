"""Reconcile the pipeline against a company's reference dataset (built from its statements).

Usage: python evaluation/verification/reconcile.py CRM     (or ADBE)
Reference: evaluation/verification/<TICKER>_reference.csv, from build_reference.py.
Actual: the pipeline in fixture mode on the unmodified SEC responses in tests/fixtures/real.

Three kinds of check:
  Reported         every reference row: the value the pipeline selects for that line item and
                   exact period, as of the filing date of the filing the row was read from.
  Displayed        every value shown by every analysis (each comparison) of each filing of the
                   fiscal year under test: quarters, years, instants and derived measures. The
                   expected value comes from the reference as of that filing's date: a printed
                   3-month column where there is one, otherwise the year-to-date difference
                   (Q4 = fiscal year - nine months), and ratios computed from reference figures.
  Export           every checked displayed value appears unchanged, with sources, in the
                   export's "Values and sources" sheet.

Tolerances: USD |diff| <= 500,000 (statements print millions); ratios |diff| <= 0.0001.
A missing or not-meaningful actual value never passes. A displayed value with no reference
figure to check it against (e.g. a line the statement does not print) is listed as
NO REFERENCE and not counted as a pass.
"""

from __future__ import annotations

import csv
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

os.environ.setdefault("EM_MODE", "fixture")
os.environ.setdefault("EM_FIXTURE_DIR", str(ROOT / "tests" / "fixtures" / "real"))
os.environ.setdefault("EM_DATA_DIR", str(ROOT / "data" / "verification"))

from companies import COMPANIES as REF_COMPANIES  # noqa: E402

from earnings_monitor.analysis import analyze, available_comparisons  # noqa: E402
from earnings_monitor.config import COMPANIES, load_settings  # noqa: E402
from earnings_monitor.exports.tables import values_frame  # noqa: E402
from earnings_monitor.financial_normalization.metrics import METRICS  # noqa: E402
from earnings_monitor.financial_normalization.selection import FactSelector  # noqa: E402
from earnings_monitor.pipeline import load_company  # noqa: E402

USD_TOL = 500_000.0
RATIO_TOL = 1e-4
RATIOS = {"operating_margin": ("operating_income", "revenue"), "net_margin": ("net_income", "revenue"),
          "cash_conversion": ("operating_cash_flow", "net_income")}


def months_between(start: date | None, end: date) -> int:
    return 0 if start is None else round(((end - start).days + 1) / 30.44)


class Reference:
    def __init__(self, path: Path):
        self.rows = list(csv.DictReader(path.open()))
        for r in self.rows:
            r["months"] = int(r["months"])
            r["period_end"] = date.fromisoformat(r["period_end"])
            r["filed"] = date.fromisoformat(r["filed"])
            r["value"] = float(r["value_musd"]) * 1e6

    def get(self, metric: str, months: int, end: date, as_of: date) -> tuple[float, str] | None:
        """The latest reference figure filed on or before as_of, with where it came from."""
        hits = [r for r in self.rows if r["metric_id"] == metric and r["months"] == months
                and abs((r["period_end"] - end).days) <= 3 and r["filed"] <= as_of]
        if not hits:
            return None
        r = max(hits, key=lambda r: r["filed"])
        return r["value"], f"{r['form']} {r['accn']} {months or 'at'}{'M' if months else ''} {end}: {r['value'] / 1e6:,.0f}M ({r['source_url']})"


def expected(ref: Reference, cal, metric: str, start: date | None, end: date, as_of: date):
    """(value, explanation) expected for a displayed value, from the reference only."""
    m = months_between(start, end)
    if metric == "free_cash_flow":
        a, b = expected(ref, cal, "operating_cash_flow", start, end, as_of), expected(ref, cal, "capex", start, end, as_of)
        return None if a is None or b is None else (a[0] - b[0], f"OCF {a[0]/1e6:,.0f}M − capex {b[0]/1e6:,.0f}M")
    if metric == "total_debt":
        a, b = expected(ref, cal, "debt_current", None, end, as_of), expected(ref, cal, "debt_noncurrent", None, end, as_of)
        return None if a is None or b is None else (a[0] + b[0], f"current {a[0]/1e6:,.0f}M + non-current {b[0]/1e6:,.0f}M")
    if metric in RATIOS:
        n, d = (expected(ref, cal, x, start, end, as_of) for x in RATIOS[metric])
        return None if n is None or d is None or d[0] <= 0 else (n[0] / d[0], f"{n[0]/1e6:,.0f}M ÷ {d[0]/1e6:,.0f}M")
    direct = ref.get(metric, m, end, as_of)
    if direct is not None or m != 3:
        return direct
    q = cal.quarter_ending(end)
    if q is None or q.quarter == 1:
        return None
    prev = cal.previous_quarter(q)
    ytd = ref.get(metric, 3 * q.quarter, end, as_of)
    ytd_prev = ref.get(metric, 3 * (q.quarter - 1), prev.end, as_of)
    if ytd is None or ytd_prev is None:
        return None
    return ytd[0] - ytd_prev[0], f"YTD {3*q.quarter}M {ytd[0]/1e6:,.0f}M − YTD {3*(q.quarter-1)}M {ytd_prev[0]/1e6:,.0f}M"


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in REF_COMPANIES:
        print(__doc__)
        return 2
    ticker = sys.argv[1]
    cfg = REF_COMPANIES[ticker]
    ref = Reference(HERE / f"{ticker}_reference.csv")
    data, stats = load_company(COMPANIES[ticker], load_settings())
    cal = data.calendar
    print(f"{ticker}: {stats['observations']:,} observations from {data.data_source}; reference rows {len(ref.rows)}")
    records: list[dict] = []

    def record(section, filing, metric, period, exp, v, kind, note=""):
        tol = RATIO_TOL if kind == "ratio" else USD_TOL
        as_of = filing[2]
        if v is None or not v.is_available:
            status, actual, diff = "FAIL", None, None
            note += " pipeline: " + ("no value" if v is None else f"status={v.status}: " + " ".join(v.notes))
        else:
            actual, diff = v.value, v.value - exp[0]
            status = "PASS" if abs(diff) <= tol else "FAIL"
            late = [s for s in v.sources if s.filed > as_of]
            if late:
                status, note = "FAIL", note + " AVAILABILITY VIOLATION: a source was filed after the as-of date."
        records.append({"Section": section, "Filing": filing[3], "As of": as_of, "Metric": metric, "Period": period,
                        "Expected": exp[0], "Actual": actual, "Difference": diff, "Tolerance": tol, "Status": status,
                        "Expected from": exp[1], "Pipeline status": None if v is None else v.status,
                        "Pipeline concept": None if v is None else v.concept,
                        "Pipeline formula": None if v is None else v.formula, "Note": note.strip()})

    # ---- 1. Reported line items ---------------------------------------------------------------
    filings = {f[0]: (f[0], f[1], date.fromisoformat(f[2]), f[3]) for f in cfg["filings"] + cfg["prior_filings"]}
    for r in ref.rows:
        if r["metric_id"] not in METRICS:
            continue
        f = filings[r["accn"]]
        sel = FactSelector(data.obs, data.company, f[2], data.primary_documents())
        metric = METRICS[r["metric_id"]]
        end, m = r["period_end"], r["months"]
        if m == 0:
            v = sel.instant_value(metric, end, f"at {end}")
            period = f"at {end}"
        else:
            q = cal.quarter_ending(end)
            if q is None:
                record("Reported", f, r["metric_id"], f"{m}M to {end}", (r["value"], r["source_url"]), None, "usd",
                       "the pipeline's fiscal calendar has no quarter ending on this date")
                continue
            start = q.start if m == 3 else q.fy_start
            direct, notes = sel.select_exact(metric, start, end)
            v = sel._value(metric, "quarter", start, end, f"{start}..{end}", direct, notes)
            period = f"{start}..{end} ({m}M)"
        face = r["concept_on_statement"].split(":")[-1]
        note = "" if v is None or v.concept in (None, face) else f"statement line is tagged {face}; pipeline used {v.concept}"
        record("Reported", f, r["metric_id"], period, (r["value"], f"{r['line_item']} ({r['source_url']})"), v, "usd", note)

    # ---- 2. Displayed values of every analysis of the fiscal year under test ------------------
    export_rows, no_reference = [], []
    for accn, form, filed_s, label in cfg["filings"]:
        f = filings[accn]
        seen = set()
        for comp in available_comparisons(data, accn):
            a = analyze(data, accn, comp)
            assert a.as_of == f[2], (a.as_of, f[2])
            vf = values_frame(a)
            for v in a.all_values:
                key = (v.metric_id, v.period_start, v.period_end)
                if v.metric_id in ("assets", "liabilities_and_equity") or key in seen:
                    continue
                seen.add(key)
                exp = expected(ref, cal, v.metric_id, v.period_start, v.period_end, f[2])
                period = f"{v.period_label} ({v.period_start or 'at'}..{v.period_end})"
                if exp is None:
                    no_reference.append({"Filing": label, "Metric": v.metric_id, "Period": period,
                                         "Pipeline value": v.value, "Pipeline status": v.status,
                                         "Why no reference": "line not printed on the statements read"})
                    continue
                kind = "ratio" if v.metric_id in RATIOS else "usd"
                record("Displayed", f, v.metric_id, period, exp, v, kind)
                rows = vf[(vf["Metric ID"] == v.metric_id) & (vf["Period end"] == v.period_end)
                          & (vf["Period start"].isna() if v.period_start is None else vf["Period start"] == v.period_start)]
                ok = len(rows) >= 1 and all((x == v.value) or (pd.isna(x) and v.value is None) for x in rows["Value"]) \
                    and all(bool(s) for s in rows["Sources"])
                export_rows.append({"Filing": label, "Comparison": comp, "Metric": v.metric_id, "Period": period,
                                    "Value": v.value, "Export rows": len(rows), "Equal with sources": ok})

    # ---- 3. Reference-internal check: balance-sheet identity -----------------------------------
    identity = []
    for r in ref.rows:
        if r["metric_id"] == "assets":
            le = [x for x in ref.rows if x["metric_id"] == "liabilities_and_equity" and x["accn"] == r["accn"]
                  and x["period_end"] == r["period_end"]]
            identity.append({"Filing": filings[r["accn"]][3], "Date": r["period_end"], "Total assets": r["value"],
                             "Liabilities + equity": le[0]["value"] if le else None,
                             "Equal": bool(le) and le[0]["value"] == r["value"]})

    df = pd.DataFrame(records)
    counted = df
    n_pass, n_fail = int((counted["Status"] == "PASS").sum()), int((counted["Status"] == "FAIL").sum())
    bad_export = [e for e in export_rows if not e["Equal with sources"]]
    concept_notes = df[df["Note"].str.startswith("statement line is tagged")]
    summary = pd.DataFrame([
        ("Company", f"{data.company.name} ({ticker}, CIK {data.company.cik})"),
        ("Fiscal year under test", cfg["fiscal_year"]),
        ("Reference rows (read from statement pages)", len(ref.rows)),
        ("Checks made", len(df)), ("PASS", n_pass), ("FAIL", n_fail),
        ("Displayed values with no reference figure (not counted)", len(no_reference)),
        ("Reported checks where the statement line uses a different concept than the pipeline", len(concept_notes)),
        ("Exported values checked", len(export_rows)), ("Exported values that differ or lack sources", len(bad_export)),
        ("Balance-sheet identity holds in the reference", f"{sum(i['Equal'] for i in identity)}/{len(identity)}"),
        ("USD tolerance", USD_TOL), ("Ratio tolerance", RATIO_TOL),
        ("Pipeline data source", data.data_source), ("Raw companyfacts SHA-256", data.raw_sha256),
    ], columns=["Item", "Value"])
    out_x = HERE / f"{ticker}_reconciliation.xlsx"
    with pd.ExcelWriter(out_x, engine="openpyxl") as xw:
        summary.to_excel(xw, sheet_name="Summary", index=False)
        df.to_excel(xw, sheet_name="Reconciliation", index=False)
        pd.DataFrame(no_reference).to_excel(xw, sheet_name="No reference", index=False)
        pd.DataFrame(export_rows).to_excel(xw, sheet_name="Export match", index=False)
        pd.DataFrame(identity).to_excel(xw, sheet_name="Reference checks", index=False)
        pd.read_csv(HERE / f"{ticker}_reference.csv").to_excel(xw, sheet_name="Reference dataset", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(max(10, max(len(str(c.value or "")) for c in col[:40]) + 2), 60)
            ws.freeze_panes = "A2"

    def fmt(x, kind):
        return "—" if x is None or pd.isna(x) else (f"{x:.4f}" if kind else f"{x:,.0f}")

    md = [f"# {data.company.name} {cfg['fiscal_year']}: reconciliation", "",
          "Generated by `python evaluation/verification/reconcile.py " + ticker + "`. Do not edit by hand.", "",
          "| Item | Value |", "|---|---|"] + [f"| {a} | {b} |" for a, b in summary.itertuples(index=False)] + ["",
          "| Section | Filing | Metric | Period | Expected | Actual | Diff | Status | Note |", "|---|---|---|---|---|---|---|---|---|"]
    for r in records:
        k = r["Metric"] in RATIOS
        md.append(f"| {r['Section']} | {r['Filing']} | {r['Metric']} | {r['Period']} | {fmt(r['Expected'], k)} | "
                  f"{fmt(r['Actual'], k)} | {fmt(r['Difference'], k)} | {r['Status']} | {r['Note']} |")
    if no_reference:
        md += ["", "## Displayed values with no reference figure", "", "| Filing | Metric | Period | Pipeline value | Status |",
               "|---|---|---|---|---|"] + [f"| {x['Filing']} | {x['Metric']} | {x['Period']} | {fmt(x['Pipeline value'], False)} | {x['Pipeline status']} |"
                                           for x in no_reference]
    (HERE / f"{ticker}_reconciliation.md").write_text("\n".join(md) + "\n")
    print(summary.to_string(index=False))
    if n_fail:
        print("\nFAILURES:")
        print(df[df["Status"] == "FAIL"][["Section", "Filing", "Metric", "Period", "Expected", "Actual", "Note"]].to_string(index=False))
    if bad_export:
        print("\nEXPORT MISMATCHES:", pd.DataFrame(bad_export).to_string(index=False))
    return 0 if n_fail == 0 and not bad_export else 1


if __name__ == "__main__":
    sys.exit(main())
