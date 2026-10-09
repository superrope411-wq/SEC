"""CSV and Excel exports built from an Analysis. Values are unscaled, exactly as computed;
every row carries the sources needed to check it on EDGAR."""

from __future__ import annotations

import io

import pandas as pd

from earnings_monitor import PIPELINE_VERSION
from earnings_monitor.analysis import Analysis
from earnings_monitor.calculations.flags import RULES
from earnings_monitor.calculations.measures import MEASURE_DEFINITIONS
from earnings_monitor.financial_normalization.metrics import DISPLAY_METRICS, METRICS
from earnings_monitor.models import MetricValue


def _period(v: MetricValue) -> str:
    return f"{v.period_start}..{v.period_end}" if v.period_start else f"at {v.period_end}"


def _sources(v: MetricValue) -> str:
    return "; ".join(f"{s.form} {s.accn} filed {s.filed}: {s.concept} {s.period_start or ''}..{s.period_end} = {s.value:,.0f} ({s.url})"
                     for s in v.sources)


def changes_frame(a: Analysis) -> pd.DataFrame:
    rows = []
    for c in a.changes:
        rows.append({
            "Metric": c.metric_label, "Metric ID": c.metric_id, "Unit": c.unit, "Comparison": c.comparison,
            "Current period": c.current.period_label, "Current value": c.current.value, "Current status": c.current.status,
            "Prior period": c.prior.period_label, "Prior value": c.prior.value, "Prior status": c.prior.status,
            "Change": c.abs_change,
            "Change unit": "percentage points" if c.change_kind == "percentage_points" else c.unit,
            "Percent change": c.pct_change, "Note": c.note,
            "Current XBRL concept": c.current.concept or "", "Prior XBRL concept": c.prior.concept or "",
            "Current formula": c.current.formula or "", "Current sources": _sources(c.current),
            "Prior sources": _sources(c.prior),
        })
    return pd.DataFrame(rows)


def values_frame(a: Analysis) -> pd.DataFrame:
    """One row per displayed value (current and prior), with formula, inputs and every source fact."""
    rows = []
    for v in a.all_values:
        rows.append({
            "Metric": v.metric_label, "Metric ID": v.metric_id, "Period": v.period_label,
            "Period start": v.period_start, "Period end": v.period_end, "Basis": v.basis, "Unit": v.unit,
            "Value": v.value, "Status": v.status, "XBRL concept": v.concept or "", "Formula": v.formula or "",
            "Inputs": "; ".join(f"{k} = {x:,.4f}" if abs(x) < 10 else f"{k} = {x:,.0f}" for k, x in v.input_values.items()),
            "Sources": _sources(v), "Why this fact": v.selection_reason,
            "Restated": v.restated, "Originally reported": v.originally_reported, "Notes": " ".join(v.notes),
        })
    return pd.DataFrame(rows)


def findings_frame(a: Analysis) -> pd.DataFrame:
    return pd.DataFrame([{"Priority": f.priority, "Rule": f.rule_id, "Finding": f.title, "Why": f.why,
                          "Metrics": ", ".join(f.metric_ids)} for f in a.findings],
                        columns=["Priority", "Rule", "Finding", "Why", "Metrics"])


def issues_frame(a: Analysis, info: bool) -> pd.DataFrame:
    keep = [i for i in a.issues if (i.severity == "info") == info]
    return pd.DataFrame([{"Severity": i.severity, "Code": i.code, "Message": i.message, "Metric": i.metric_id or "",
                          "Period": i.period_label or ""} for i in keep],
                        columns=["Severity", "Code", "Message", "Metric", "Period"])


def definitions_frame() -> pd.DataFrame:
    rows = [{"Metric": METRICS[m].label, "Metric ID": m, "Kind": "reported", "Unit": METRICS[m].unit,
             "Definition": METRICS[m].definition, "Approved XBRL concepts (in order)": ", ".join(METRICS[m].concepts),
             "Notes": METRICS[m].notes} for m in DISPLAY_METRICS]
    rows += [{"Metric": label, "Metric ID": mid, "Kind": "derived", "Unit": unit, "Definition": formula,
              "Approved XBRL concepts (in order)": "", "Notes": ""}
             for mid, (label, unit, formula) in MEASURE_DEFINITIONS.items()]
    rows += [{"Metric": r.description, "Metric ID": r.metric_id, "Kind": "flag rule", "Unit": "",
              "Definition": f"Rule {r.id}: threshold {r.threshold}, priority {r.priority}",
              "Approved XBRL concepts (in order)": "", "Notes": ""} for r in RULES]
    return pd.DataFrame(rows)


def summary_frame(a: Analysis) -> pd.DataFrame:
    source = ("LOCAL FIXTURE files (saved SEC responses), not downloaded in this run"
              if a.data_source == "fixture" else "SEC EDGAR API")
    items = [
        ("Company", f"{a.company.name} ({a.company.ticker}), CIK {a.company.cik}"),
        ("Filing", f"{a.filing.form} {a.filing.accn}"),
        ("Filing URL", a.filing.url),
        ("Filing date (as-of)", str(a.as_of)),
        ("Fiscal period", a.quarter.long_label),
        ("Comparison", a.comparison_label),
        ("Current", a.current_label),
        ("Prior", a.prior_label),
        ("Data source", source),
        ("Raw companyfacts SHA-256", a.raw_sha256),
        ("Fetched at", a.fetched_at),
        ("Pipeline version", PIPELINE_VERSION),
        ("Scale", "USD values are unscaled (whole dollars as reported in XBRL); ratios are fractions"),
        ("Point-in-time rule", "Only facts filed on or before the as-of date are used"),
    ]
    return pd.DataFrame(items, columns=["Item", "Value"])


def to_csv(a: Analysis) -> bytes:
    return changes_frame(a).to_csv(index=False).encode("utf-8")


def to_excel(a: Analysis) -> bytes:
    buf = io.BytesIO()
    sheets = {
        "Summary": summary_frame(a), "Changes": changes_frame(a), "Findings": findings_frame(a),
        "Values and sources": values_frame(a), "Unresolved issues": issues_frame(a, info=False),
        "Checks passed": issues_frame(a, info=True), "Definitions": definitions_frame(),
    }
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
            ws = xw.sheets[name]
            for col in ws.columns:
                width = max(len(str(c.value or "")) for c in col[:50]) + 2
                ws.column_dimensions[col[0].column_letter].width = min(max(width, 10), 70)
            ws.freeze_panes = "A2"
    return buf.getvalue()
