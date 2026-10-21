"""Compare-companies page. Rendering only; logic is in earnings_monitor.comparison."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from earnings_monitor.comparison import COMPARE_METRICS, CrossCompany


def _fmt(v: dict) -> str:
    if v.get("change") is None:
        return "—" if v.get("status") in ("missing", None) else "n/m"
    if v["change_kind"] == "percent":
        return f"{v['change']:+.1%}"
    return f"{v['value']:.1%} ({v['change']:+.1f} pp)"


def render(cc: CrossCompany) -> None:
    for w in cc.warnings:
        st.warning(w)
    rows = []
    for c in cc.columns:
        a = c.alignment
        rows.append({"Company": f"{c.name} ({c.ticker})", "Period": a.label, "Start": str(a.start), "End": str(a.end),
                     "Days": a.length_days, "Overlap with anchor (days)": a.overlap_days,
                     "End offset (days)": a.offset_days, "Months shared": ", ".join(a.shared_months),
                     "Filing": c.filing_accn or "—", "Filed (as-of)": str(c.filed) if c.filed else "—"})
    st.markdown("**Periods compared**")
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    word = "same quarter a year earlier" if cc.basis == "quarter" else "prior fiscal year"
    st.markdown(f"**Each company against its own {word}**")
    table = {"Measure": []}
    for c in cc.columns:
        table[c.ticker] = []
    for m, kind in COMPARE_METRICS:
        label = next((c.values[m]["label"] for c in cc.columns if m in c.values), m)
        table["Measure"].append(f"{label} ({'growth' if kind == 'growth' else 'level, change in pp'})")
        for c in cc.columns:
            table[c.ticker].append(_fmt(c.values[m]) if m in c.values else "—")
    st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")
    st.caption("Growth rates and ratios are compared because they are less sensitive to a one-month offset than dollar "
               "totals; they still describe different calendar windows. Dollar totals are not ranked across companies. "
               "Business mixes differ (Microsoft includes hardware, gaming and LinkedIn). 'n/m' = not meaningful "
               "(e.g. a negative or zero denominator). Each company's values are as of its own filing date.")
    for c in cc.columns:
        if c.note:
            st.info(f"{c.ticker}: {c.note}")
