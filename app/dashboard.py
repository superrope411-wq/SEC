"""Analyst dashboard (Streamlit). Business logic lives in earnings_monitor; this file only renders.

Run:  streamlit run app/dashboard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from earnings_monitor import PIPELINE_VERSION  # noqa: E402
from earnings_monitor.analysis import COMPARISONS, AnalysisError, analyze, available_comparisons  # noqa: E402
from earnings_monitor.calculations.flags import RULES  # noqa: E402
from earnings_monitor.config import COMPANIES, ConfigError, load_settings  # noqa: E402
from earnings_monitor.exports.tables import definitions_frame, to_csv, to_excel  # noqa: E402
from earnings_monitor.ingestion.sec_client import SecError  # noqa: E402
from earnings_monitor.models import Change, MetricValue  # noqa: E402
from earnings_monitor.pipeline import load_company  # noqa: E402
from earnings_monitor.evidence.retrieve import build_index  # noqa: E402
from earnings_monitor.explain.store import AiStore  # noqa: E402
from earnings_monitor.comparison import compare_companies  # noqa: E402
from earnings_monitor.disclosure_diff.service import DisclosureError, compare_filings  # noqa: E402
from earnings_monitor.review import ReviewStore, financial_key  # noqa: E402
import compare_page  # noqa: E402
import disclosure_panel  # noqa: E402
import explain_panel  # noqa: E402
import review_controls  # noqa: E402

st.set_page_config(page_title="Quarterly Earnings Change Monitor", layout="wide")

LINE_COLOR = "#3B6EA8"  # one series per chart, so a single neutral hue


@st.cache_resource(show_spinner="Loading SEC data…")
def _load(ticker: str, refresh_token: int):
    settings = load_settings()
    return load_company(COMPANIES[ticker], settings, refresh=refresh_token > 0)


@st.cache_resource(show_spinner="Reading the filing text…")
def _index(ticker: str, accn: str, refresh_token: int):
    """Evidence index for one filing; returns (index, error message) and never raises."""
    settings = load_settings()
    data, _ = load_company(COMPANIES[ticker], settings)
    try:
        return build_index(data, accn, settings), None
    except Exception as exc:  # missing document, network refused, parse failure
        return None, f"{type(exc).__name__}: {exc}"


@st.cache_resource(show_spinner="Comparing sections…")
def _disclosure(ticker: str, accn: str, section: str, basis: str, refresh_token: int):
    """Disclosure comparison for one filing; returns (comparison, error message) and never raises."""
    settings = load_settings()
    data, _ = load_company(COMPANIES[ticker], settings)
    try:
        return compare_filings(data, accn, section, settings, basis), None
    except DisclosureError as exc:
        return None, str(exc)
    except Exception as exc:  # missing document, network refused, parse failure
        return None, f"Could not compare: {type(exc).__name__}: {exc}"


@st.cache_resource
def _review_store(data_dir: str):
    return ReviewStore(Path(data_dir) / "reviews.sqlite")


def _reviews():
    return _review_store(str(load_settings().data_dir))


def usd_scale(values) -> tuple[float, str]:
    """Pick one display scale for a set of USD values so a table reads consistently."""
    big = max((abs(x) for x in values if x is not None), default=0)
    if big >= 1e9:
        return 1e9, "USD billions"
    if big >= 1e6:
        return 1e6, "USD millions"
    return 1.0, "USD"


def fmt_usd(x: float | None, scale: float, sign: bool = False) -> str:
    if x is None:
        return "—"
    spec = "+,.2f" if sign else ",.2f"
    return format(x / scale, spec) if scale > 1 else format(x, "+,.0f" if sign else ",.0f")


def fmt_value(v: MetricValue, scale: float) -> str:
    if v.value is None:
        return "—"
    if v.unit == "ratio":
        return f"{v.value:.1%}"
    return fmt_usd(v.value, scale)


def fmt_change(c: Change, scale: float) -> str:
    if c.abs_change is None:
        return "—"
    if c.change_kind == "percentage_points":
        return f"{c.abs_change:+.1f} pp"
    s = fmt_usd(c.abs_change, scale, sign=True)
    if c.pct_change is not None:
        s += f" ({c.pct_change:+.1%})"
    return s


def evidence(v: MetricValue) -> None:
    shown = f"{v.value:.4f}" if v.unit == "ratio" and v.value is not None else fmt_usd(v.value, 1.0)
    st.markdown(f"**{v.metric_label}**, {v.period_label}: {shown} "
                f"({'ratio' if v.unit == 'ratio' else v.unit + ', unscaled'}), status **{v.status}**")
    if v.formula:
        st.markdown(f"Formula: `{v.formula}`")
        if v.input_values:
            st.table(pd.DataFrame({"Input": list(v.input_values), "Value": [f"{x:,.4f}" if abs(x) < 10 else f"{x:,.0f}"
                                                                           for x in v.input_values.values()]}))
    if v.restated and v.originally_reported is not None:
        st.warning(f"Revised: originally reported as {v.originally_reported:,.0f}. The data does not say why "
                   "(accounting-policy change or error correction); check the filing.")
    if v.sources:
        rows = [{"XBRL concept": s.concept, "Period": f"{s.period_start or ''}..{s.period_end}".strip("."),
                 "Value": f"{s.value:,.0f}", "Form": s.form, "Accession": s.accn, "Filed": str(s.filed),
                 "Filing": s.url} for s in v.sources]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     column_config={"Filing": st.column_config.LinkColumn("Filing", display_text="open on EDGAR")})
    st.caption(f"Why this fact: {v.selection_reason}")
    for n in v.notes:
        st.caption(f"Note: {n}")


# ---------------------------------------------------------------------------------------------
st.title("Quarterly Earnings Change Monitor")
st.caption("Deterministic SEC XBRL pipeline. Every number links to its filing. "
           "AI is used only in the Explanations tab, only on request, and only to explain verified numbers.")

if "refresh" not in st.session_state:
    st.session_state.refresh = 0
with st.sidebar:
    view = st.radio("View", ["One company", "Compare companies"], horizontal=True)

if view == "Compare companies":
    st.subheader("Compare companies")
    st.caption("The three companies' fiscal quarters never line up: Microsoft's end in Mar/Jun/Sep/Dec, Salesforce's in "
               "Jan/Apr/Jul/Oct, Adobe's in late Feb/May/Aug/Nov. Pick an anchor company and period; each other company "
               "contributes its period with the most calendar overlap, and every offset is shown.")
    try:
        datasets = {t: _load(t, st.session_state.refresh)[0] for t in COMPANIES}
    except (ConfigError, SecError, FileNotFoundError) as exc:
        st.error(f"Could not load SEC data: {exc}")
        st.stop()
    if any(d.data_source == "fixture" for d in datasets.values()):
        st.warning("FIXTURE MODE: data comes from local files, not from SEC in this run.")
    with st.sidebar:
        anchor = st.selectbox("Anchor company", list(COMPANIES), format_func=lambda t: f"{COMPANIES[t].name} ({t})")
        basis = st.radio("Basis", ["quarter", "annual"], format_func={"quarter": "Quarter", "annual": "Fiscal year"}.get)
        cal = datasets[anchor].calendar
        reported = {r.report_date for r in datasets[anchor].filings.itertuples() if r.report_date is not None}
        periods = [p for p in (cal.quarters if basis == "quarter" else cal.years) if p.end in reported][::-1]
        period = st.selectbox("Anchor period", periods, format_func=lambda p: p.long_label)
    try:
        compare_page.render(compare_companies(datasets, anchor, period.end, basis))
    except Exception as exc:
        st.error(f"Comparison failed: {type(exc).__name__}: {exc}")
    st.stop()

with st.sidebar:
    st.header("Selection")
    ticker = st.selectbox("Company", list(COMPANIES), format_func=lambda t: f"{COMPANIES[t].name} ({t})")
    if st.button("Check SEC for new filings", help="Re-downloads this company's data from SEC EDGAR."):
        st.session_state.refresh += 1
        _load.clear()

try:
    data, stats = _load(ticker, st.session_state.refresh)
except ConfigError as exc:
    st.error(f"Configuration problem: {exc}")
    st.stop()
except (SecError, FileNotFoundError) as exc:
    st.error(f"Could not load SEC data: {exc}")
    st.info("If SEC is unreachable, set EM_MODE=fixture and EM_FIXTURE_DIR to a folder of saved SEC responses. "
            "Fixture mode is labeled on every screen and never substitutes made-up numbers.")
    st.stop()

if data.data_source == "fixture":
    st.warning("FIXTURE MODE: data comes from local files, not from SEC in this run.")

with st.sidebar:
    filings = data.filings.copy()
    labels = {}
    for r in filings.itertuples():
        q = data.calendar.quarter_ending(r.report_date) if r.report_date else None
        labels[r.accn] = f"{r.form}  {q.label if q else r.report_date}  (filed {r.filed})"
    accn = st.selectbox("Filing", list(labels), format_func=labels.get)
    comps = available_comparisons(data, accn)
    comparison = st.selectbox("Comparison", comps, index=comps.index("yoy") if "yoy" in comps else 0,
                              format_func=COMPARISONS.get)
    st.caption(f"Data: {'fixture' if data.data_source == 'fixture' else 'SEC EDGAR'} · fetched {data.fetched_at[:8]} · "
               f"{stats['observations']:,} facts · load {stats['seconds']:.2f}s · pipeline {PIPELINE_VERSION}")

try:
    a = analyze(data, accn, comparison)
except AnalysisError as exc:
    st.error(str(exc))
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Filing", f"{a.filing.form}")
c2.metric("Filing date (as-of)", str(a.filing.filed))
c3.metric("Fiscal period", a.quarter.label)
c4.metric("Comparison", {"sequential": "Sequential", "yoy": "Year over year", "annual": "Annual"}[a.comparison])
st.markdown(f"**{a.current_label}** vs **{a.prior_label}** · "
            f"[Open filing {a.filing.accn} on EDGAR]({a.filing.url}) · "
            "All values are as reported in filings made on or before the filing date; later revisions are excluded.")

warnings = [i for i in a.issues if i.severity in ("error", "warning") and i.code != "fixture_mode"]
errors = [i for i in warnings if i.severity == "error"]
if errors:
    st.error(f"{len(errors)} validation error(s). See 'Validation' below.")

reviews = _reviews()
tab_changes, tab_explain, tab_findings, tab_disclosure, tab_trends, tab_validation, tab_defs = st.tabs(
    ["Financial changes", "Explanations", f"Findings ({len(a.findings)})", "Disclosure changes", "Trends",
     f"Validation ({len(warnings)})", "Definitions"])

with tab_changes:
    scale, scale_label = usd_scale([c.current.value for c in a.changes if c.unit != "ratio"] +
                                   [c.prior.value for c in a.changes if c.unit != "ratio"])
    rows = []
    for c in a.changes:
        rows.append({"Metric": c.metric_label, "Current": fmt_value(c.current, scale), "Prior": fmt_value(c.prior, scale),
                     "Change": fmt_change(c, scale), "Status": c.current.status, "Note": c.note or ""})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption(f"USD values in {scale_label}; exports carry unscaled values. "
               "Ratios change in percentage points (pp). 'derived' = computed from reported facts; the formula is shown in the evidence.")
    st.subheader("Evidence")
    pick = st.selectbox("Show evidence for", [c.metric_label for c in a.changes])
    c = next(x for x in a.changes if x.metric_label == pick)
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("Current period")
        evidence(c.current)
    with col_b:
        st.markdown("Prior period")
        evidence(c.prior)

with tab_explain:
    try:
        ai_store = AiStore(load_settings().data_dir / "ai_cache.sqlite")
        index, index_error = _index(ticker, accn, st.session_state.refresh)
        explain_panel.render(a, index, index_error, ai_store)
        explain_panel.usage_summary(ai_store)
    except Exception as exc:  # explanations are optional; the tables above must keep working
        st.error(f"Explanations unavailable: {type(exc).__name__}: {exc}")

with tab_findings:
    st.caption("Flags are rule-based and neutral: a flag means 'worth a look', not good or bad. "
               "Thresholds are listed under Definitions.")
    if not a.findings:
        st.info("No rule thresholds were crossed for this comparison.")
    for f in a.findings:
        fkey = financial_key(a.company.ticker, a.filing.accn, a.comparison, f.rule_id)
        status, _ = reviews.get(fkey)
        with st.expander(f"{review_controls.badge(status)}[P{f.priority}] {f.title}", expanded=f.priority == 1 and status == "new"):
            st.write(f.why)
            review_controls.control(reviews, fkey, a.company.ticker, "financial", f.title)
            for m in f.metric_ids:
                ch = next((x for x in a.changes if x.metric_id == m), None)
                if ch:
                    st.markdown(f"*Evidence for {ch.metric_label}*")
                    evidence(ch.current)

with tab_disclosure:
    st.caption("Compares the same section of two filings of the same form. Formatting, reordering, page breaks and "
               "routine date or number updates are suppressed; what remains is ranked by how much language is new or dropped.")
    section, dbasis = disclosure_panel.selectors(a.filing.form)
    comp, derr = _disclosure(ticker, accn, section, dbasis, st.session_state.refresh)
    disclosure_panel.render(comp, derr, reviews)

with tab_trends:
    st.caption("Standalone quarters, as of the selected filing date. Hollow markers are derived values.")
    metric_ids = list(dict.fromkeys(a.trend["metric_id"]))
    labels_by_id = dict(zip(a.trend["metric_id"], a.trend["metric_label"]))
    chosen = st.multiselect("Metrics", metric_ids, default=["revenue", "operating_margin", "free_cash_flow"],
                            format_func=labels_by_id.get)
    cols = st.columns(2)
    for i, m in enumerate(chosen):
        t = a.trend[a.trend["metric_id"] == m]
        unit = t["unit"].iloc[0]
        tscale, tscale_label = usd_scale(list(t["value"]))
        y = t["value"] * 100 if unit == "ratio" else t["value"] / tscale
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=t["period_label"], y=y, mode="lines+markers", name=labels_by_id[m],
            line=dict(color=LINE_COLOR, width=2),
            marker=dict(size=8, color=[LINE_COLOR if s == "reported" else "white" for s in t["status"]],
                        line=dict(color=LINE_COLOR, width=2)),
            customdata=list(zip(t["period_long_label"], t["status"])),
            hovertemplate="%{customdata[0]}<br>%{y:,.1f}<br>%{customdata[1]}<extra></extra>",
        ))
        fig.update_layout(title=labels_by_id[m], height=300, margin=dict(l=40, r=20, t=40, b=40),
                          yaxis_title="percent" if unit == "ratio" else tscale_label,
                          xaxis_title="Fiscal quarter", showlegend=False,
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        fig.update_yaxes(gridcolor="rgba(128,128,128,0.2)", zeroline=False)
        fig.update_xaxes(showgrid=False)
        cols[i % 2].plotly_chart(fig, width="stretch")

with tab_validation:
    if not warnings:
        st.success("No warnings.")
    for i in warnings:
        (st.error if i.severity == "error" else st.warning)(f"**{i.code}** {i.message}")
    with st.expander("Checks passed"):
        for i in a.issues:
            if i.severity == "info":
                st.write(f"✓ {i.message}")

with tab_defs:
    st.dataframe(definitions_frame(ticker), hide_index=True, width="stretch")
    st.markdown("**Flag rules**")
    st.table(pd.DataFrame([{"Rule": r.id, "Metric": r.metric_id, "Threshold": r.threshold, "Priority": r.priority,
                            "Description": r.description} for r in RULES]))

st.divider()
d1, d2 = st.columns(2)
stem = f"{a.company.ticker}_{a.filing.accn}_{a.comparison}"
review_map = {r["key"]: (r["status"], r["note"]) for r in reviews.all(a.company.ticker)}
d1.download_button("Download Excel workbook", to_excel(a, review_map), f"{stem}.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
d2.download_button("Download changes CSV", to_csv(a), f"{stem}.csv", "text/csv")
