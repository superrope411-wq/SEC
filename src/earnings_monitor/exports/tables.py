"""CSV and Excel exports built from an Analysis. Values are unscaled, exactly as computed;
every row carries the sources needed to check it on EDGAR."""

from __future__ import annotations

import io

import pandas as pd

from earnings_monitor import PIPELINE_VERSION
from earnings_monitor.analysis import Analysis
from earnings_monitor.calculations.flags import RULES
from earnings_monitor.calculations.measures import MEASURE_DEFINITIONS
from earnings_monitor.financial_normalization.metrics import COMPANY_CONCEPTS, DISPLAY_METRICS, METRICS
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
            "Revised after first report": v.restated, "Originally reported": v.originally_reported, "Notes": " ".join(v.notes),
        })
    return pd.DataFrame(rows)


def findings_frame(a: Analysis, reviews: dict[str, tuple[str, str]] | None = None) -> pd.DataFrame:
    """Findings, with the analyst's review status when a {key: (status, note)} map is given."""
    from earnings_monitor.review import STATUS_LABELS, financial_key
    reviews = reviews or {}
    rows = []
    for f in a.findings:
        status, note = reviews.get(financial_key(a.company.ticker, a.filing.accn, a.comparison, f.rule_id), ("new", ""))
        rows.append({"Priority": f.priority, "Rule": f.rule_id, "Finding": f.title, "Why": f.why,
                     "Metrics": ", ".join(f.metric_ids), "Review status": STATUS_LABELS[status], "Review note": note})
    return pd.DataFrame(rows, columns=["Priority", "Rule", "Finding", "Why", "Metrics", "Review status", "Review note"])


def issues_frame(a: Analysis, info: bool) -> pd.DataFrame:
    keep = [i for i in a.issues if (i.severity == "info") == info]
    return pd.DataFrame([{"Severity": i.severity, "Code": i.code, "Message": i.message, "Metric": i.metric_id or "",
                          "Period": i.period_label or ""} for i in keep],
                        columns=["Severity", "Code", "Message", "Metric", "Period"])


def definitions_frame(ticker: str | None = None) -> pd.DataFrame:
    rows = [{"Metric": METRICS[m].label, "Metric ID": m, "Kind": "reported", "Unit": METRICS[m].unit,
             "Definition": METRICS[m].definition, "Approved XBRL concepts (in order)": ", ".join(METRICS[m].concepts),
             "Notes": METRICS[m].notes} for m in DISPLAY_METRICS]
    for t, overrides in COMPANY_CONCEPTS.items():
        if ticker and t != ticker:
            continue
        for m, (concepts, why) in overrides.items():
            rows.append({"Metric": f"{METRICS[m].label} ({t} only)", "Metric ID": m, "Kind": "company-specific concepts",
                         "Unit": METRICS[m].unit, "Definition": METRICS[m].definition,
                         "Approved XBRL concepts (in order)": ", ".join(concepts), "Notes": why})
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


def to_excel(a: Analysis, reviews: dict[str, tuple[str, str]] | None = None) -> bytes:
    sheets = {
        "Summary": summary_frame(a), "Changes": changes_frame(a), "Findings": findings_frame(a, reviews),
        "Values and sources": values_frame(a), "Unresolved issues": issues_frame(a, info=False),
        "Checks passed": issues_frame(a, info=True), "Definitions": definitions_frame(a.company.ticker),
    }
    return write_workbook(sheets)


def write_workbook(sheets: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
            ws = xw.sheets[name]
            for col in ws.columns:
                width = max(len(str(c.value or "")) for c in col[:50]) + 2
                ws.column_dimensions[col[0].column_letter].width = min(max(width, 10), 70)
            ws.freeze_panes = "A2"
    return buf.getvalue()


# ---- disclosure comparison ------------------------------------------------------------------

def disclosure_frame(comp, reviews: dict[str, tuple[str, str]] | None = None) -> pd.DataFrame:
    """One row per substantive disclosure change, ranked, with excerpts, links and review status."""
    from earnings_monitor.review import STATUS_LABELS, disclosure_key
    reviews = reviews or {}
    rows = []
    for rank, r in enumerate(comp.ranked, start=1):
        c, sig = r.change, r.significance
        key = disclosure_key(comp.company, comp.new.accn, comp.old.accn, comp.section_id, c.kind,
                             c.old.norm if c.old else "", c.new.norm if c.new else "")
        status, note = reviews.get(key, ("new", ""))
        rows.append({
            "Rank": rank, "Change": c.kind, "Section": comp.section_title, "Heading": (c.new or c.old).heading,
            "Why it may matter": sig.reason, "Topics": ", ".join(t.label for t in sig.tags),
            "New language (words)": sig.words_added, "Dropped language (words)": sig.words_removed,
            "Similarity": c.similarity, "Before": c.old.text if c.old else "", "After": c.new.text if c.new else "",
            "Before link": c.old.url if c.old else "", "After link": c.new.url if c.new else "",
            "Evidence IDs (after)": " ".join(c.new.evidence_ids) if c.new else "",
            "Evidence IDs (before)": " ".join(c.old.evidence_ids) if c.old else "",
            "Note": c.note, "Review status": STATUS_LABELS[status], "Review note": note,
        })
    return pd.DataFrame(rows)


def disclosure_summary_frame(comp) -> pd.DataFrame:
    items = [("Company", comp.company), ("Section", comp.section_title), ("Basis", comp.basis),
             ("Later filing", f"{comp.new.form} {comp.new.accn} filed {comp.new.filed} ({comp.new.period_label}) {comp.new.url}"),
             ("Earlier filing", f"{comp.old.form} {comp.old.accn} filed {comp.old.filed} ({comp.old.period_label}) {comp.old.url}"),
             ("Status", comp.status), ("Message", comp.message)]
    if comp.diff is not None:
        items += [("Paragraphs (earlier, later)", f"{comp.diff.old_count}, {comp.diff.new_count}")]
        items += [(f"Suppressed as noise: {k}", v) for k, v in comp.noise.items()]
        items += [("Substantive changes listed", len(comp.ranked))]
        items += [("Method", "Deterministic paragraph matching; see docs/DISCLOSURE_CHANGES.md. "
                             "Topic tags are keyword rules and do not judge good or bad.")]
    return pd.DataFrame(items, columns=["Item", "Value"])


def disclosure_to_excel(comp, reviews=None) -> bytes:
    return write_workbook({"Summary": disclosure_summary_frame(comp), "Changes": disclosure_frame(comp, reviews)})
