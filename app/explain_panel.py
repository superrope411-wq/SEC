"""Dashboard panel for evidence-backed explanations. Rendering only; logic is in earnings_monitor.explain.

Nothing here can stop the rest of the dashboard: every failure is shown as a message inside
the panel. No model call happens unless the analyst presses "Generate explanation".
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from earnings_monitor.analysis import Analysis
from earnings_monitor.evidence.retrieve import EvidenceIndex
from earnings_monitor.explain.llm import AiSettings, api_key_present
from earnings_monitor.explain.schema import Explanation
from earnings_monitor.explain.service import generate, from_cache, prepare, question_metrics
from earnings_monitor.explain.store import AiStore

STATUS_STYLE = {"supported": st.success, "inferred": st.info, "conflicting evidence": st.warning,
                "insufficient evidence": st.warning}


def suggested_questions(a: Analysis) -> list[str]:
    word = {"sequential": "from the previous quarter", "yoy": "from the same quarter last year",
            "annual": "from the prior fiscal year"}[a.comparison]
    return [f"Why did {c.metric_label.lower()} change {word}?" for c in a.changes if c.abs_change]


def _fmt_money(v: float | None, unit: str) -> str:
    if v is None:
        return "n/a"
    return f"${v / 1e6:,.0f}M" if unit == "USD" else f"{v * 100:.2f}%"


def _render(ex: Explanation, index: EvidenceIndex) -> None:
    STATUS_STYLE[ex.status](f"**{ex.status.capitalize()}** — {ex.status_reason}")
    if ex.error:
        st.error(ex.error)
    if ex.interpretation:
        st.markdown(f"**Question read as:** {ex.interpretation}")
    if ex.ambiguity:
        st.warning(f"Ambiguous question: {ex.ambiguity}")
    metrics = question_metrics(ex.question) or [c.metric_id for c in ex.calculated]
    st.markdown("**Calculated change** (verified pipeline, not the model)")
    st.dataframe(pd.DataFrame([{
        "Metric": c.metric_label, "Current": _fmt_money(c.current_value, c.unit), "Prior": _fmt_money(c.prior_value, c.unit),
        "Change": ("n/a" if c.change_amount is None else f"{c.change_amount:+.2f} pp" if c.change_kind == "percentage_points"
                   else _fmt_money(c.change_amount, c.unit)),
        "Percent change": "" if c.change_percent is None else f"{c.change_percent * 100:+.1f}%",
    } for c in ex.calculated if c.metric_id in metrics]), hide_index=True, use_container_width=True)

    mgmt = [s for s in ex.accepted if s.kind == "management"]
    infs = [s for s in ex.accepted if s.kind == "inference"]
    st.markdown("**What the filing says**")
    if not mgmt:
        st.caption("No management statement passed the checks.")
    for s in mgmt:
        st.markdown(f"- {s.text}")
        for c in s.citations:
            st.caption(f"“{c.citation.quote}” — {c.section}, page {c.page or '?'} · "
                       f"[{c.citation.evidence_id}]({c.url})")
    st.markdown("**Inference** (not stated in the filing; drawn from the cited evidence)")
    if not infs:
        st.caption("None.")
    for s in infs:
        st.markdown(f"- *Inference:* {s.text}")
        st.caption(f"Based on {', '.join(s.based_on)}. Reasoning: {s.reasoning}")
    if ex.insufficient_evidence_reason and ex.status == "insufficient evidence":
        st.markdown(f"**Why there is no answer:** {ex.insufficient_evidence_reason}")
    if ex.unresolved_questions:
        st.markdown("**Open questions:** " + "; ".join(ex.unresolved_questions))
    if ex.figures:
        st.markdown("**Numbers checked against the verified data** (metric, period, unit, value)")
        st.dataframe(pd.DataFrame([{"Number": f.figure.stated_text, "Metric": f.figure.metric_id,
                                    "Measure": f.figure.measure, "Result": f.result, "Why": "; ".join(f.reasons),
                                    "Evidence": f.figure.evidence_id} for f in ex.figures]),
                     hide_index=True, use_container_width=True)
    if ex.rejected:
        with st.expander(f"Rejected by the checks ({len(ex.rejected)})"):
            for s in ex.rejected:
                st.markdown(f"- ~~{s.text}~~ ({s.kind}) — {'; '.join(s.reasons)}")
    if ex.usage:
        u = ex.usage
        st.caption(f"{u.model} · {u.input_tokens:,} input + {u.output_tokens:,} output tokens · ${u.cost_usd:.4f} · "
                   f"{u.latency_ms / 1000:.1f}s" + (" · from cache, no new cost" if u.cached else ""))


def render(a: Analysis, index: EvidenceIndex | None, index_error: str | None, store: AiStore) -> None:
    st.caption("Explanations of the verified changes, built only from cited passages of this filing. "
               "The model never supplies numbers; every statement is checked in code before it is shown, and "
               "anything the filing does not say is labeled as inference.")
    if index_error:
        st.warning(f"Filing text unavailable, so no evidence can be cited: {index_error}")
    options = suggested_questions(a) + ["Custom question…"]
    choice = st.selectbox("Question", options)
    question = st.text_input("Your question", placeholder="e.g. What drove operating income growth?") \
        if choice == "Custom question…" else choice
    if not question:
        return
    settings = AiSettings.from_env()
    try:
        prep = prepare(question, a, index, settings)
    except Exception as exc:  # the panel must never take the dashboard down
        st.error(f"Could not prepare evidence: {exc}")
        return
    if prep.gate_reason:
        st.warning(f"**Insufficient evidence** — {prep.gate_reason}")
        st.caption("Decided without a model call.")
        return

    with st.expander(f"Evidence passages offered to the model ({len(prep.hits)})"):
        for h in prep.hits:
            p = h.passage
            st.markdown(f"`{p.evidence_id}` · {p.section_title} · page {p.page or '?'} · "
                        f"periods {', '.join(p.periods) or 'not stated'} · [open in filing]({p.url})")
            st.caption(p.text[:700] + ("…" if len(p.text) > 700 else ""))

    ex = from_cache(prep, store)
    if ex is None:
        spent = store.spent_usd()
        worst = settings.worst_case_cost(len(prep.user) + 4000)
        if not api_key_present():
            st.info("Set ANTHROPIC_API_KEY to generate explanations. The calculated changes and the evidence "
                    "passages above do not need it.")
            return
        st.caption(f"Model {settings.model} · this call costs at most about ${worst:.2f} · "
                   f"spent so far ${spent:.2f} of the ${settings.budget_usd:.2f} cap")
        if not st.button("Generate explanation", type="primary"):
            return
        with st.spinner("Asking the model and checking its citations…"):
            ex = generate(prep, store, settings)
    _render(ex, index)


def usage_summary(store: AiStore) -> None:
    s = store.summary()
    st.caption(f"AI usage: {s['api_calls']} API calls · ${s['cost_usd']:.4f} · {s['input_tokens']:,} in / "
               f"{s['output_tokens']:,} out tokens · {s['cache_hits']} cache hits · {s['cached_answers']} cached answers")
