"""Dashboard panel for disclosure changes. Rendering only; logic is in earnings_monitor.disclosure_diff."""

from __future__ import annotations

import html

import streamlit as st

from earnings_monitor.disclosure_diff.compare import Change
from earnings_monitor.disclosure_diff.service import BASES, SECTIONS, DisclosureComparison
from earnings_monitor.exports.tables import disclosure_to_excel
from earnings_monitor.review import ReviewStore, disclosure_key
import review_controls

KIND_LABEL = {"added": "Added", "removed": "Removed", "changed": "Changed"}


def highlighted(c: Change) -> tuple[str, str]:
    """Before/after HTML with removed words struck through in the old text and added words marked in the new."""
    if not c.ops:
        return (html.escape(c.old.text) if c.old else ""), (html.escape(c.new.text) if c.new else "")
    before, after = [], []
    for o in c.ops:
        if o.op == "equal":
            before.append(html.escape(o.old))
            after.append(html.escape(o.new))
        else:
            if o.old:
                before.append(f"<del style='background:rgba(200,80,80,.25)'>{html.escape(o.old)}</del>")
            if o.new:
                after.append(f"<ins style='background:rgba(60,160,90,.25);text-decoration:none'>{html.escape(o.new)}</ins>")
    return " ".join(before), " ".join(after)


def render(comp: DisclosureComparison | None, error: str | None, store: ReviewStore) -> None:
    if error:
        st.warning(error)
        return
    st.markdown(f"**{comp.section_title}**: {comp.new.form} filed {comp.new.filed} ({comp.new.period_label}) "
                f"vs {comp.old.form} filed {comp.old.filed} ({comp.old.period_label}) · basis: {comp.basis} · "
                f"[later filing]({comp.new.url}) · [earlier filing]({comp.old.url})")
    if comp.status != "compared":
        st.info(comp.message)
        return
    n = comp.noise
    st.caption(f"{comp.diff.old_count} → {comp.diff.new_count} paragraphs. Suppressed as noise: "
               f"{n['unchanged']} unchanged ({n['reordered']} of them moved), {n['routine_update']} with only dates or "
               f"numbers updated, {n['minor_edit']} with at most 3 words changed, {n['split_or_merge']} split, merged "
               f"or regrouped, {n['heading_renames']} heading renames. Text comparison is deterministic; topic tags "
               "are keyword rules and say what a change is about, not whether it is good or bad.")
    topics = sorted({t.label for r in comp.ranked for t in r.significance.tags})
    f1, f2, f3 = st.columns([2, 2, 1])
    kinds = f1.multiselect("Show", list(KIND_LABEL), default=list(KIND_LABEL), format_func=KIND_LABEL.get)
    pick_topics = f2.multiselect("Topics", topics)
    min_words = f3.number_input("Min. new or dropped words", 0, 500, 10, step=5)
    shown = [r for r in comp.ranked if r.change.kind in kinds
             and (r.significance.words_added + r.significance.words_removed) >= min_words
             and (not pick_topics or any(t.label in pick_topics for t in r.significance.tags))]
    st.markdown(f"**{len(shown)}** of {len(comp.ranked)} substantive changes shown, largest first.")
    reviews = {}
    for r in shown[:60]:
        c, sig = r.change, r.significance
        key = disclosure_key(comp.company, comp.new.accn, comp.old.accn, comp.section_id, c.kind,
                             c.old.norm if c.old else "", c.new.norm if c.new else "")
        status, _ = store.get(key)
        head = (c.new or c.old).heading or comp.section_title
        title = f"{review_controls.badge(status)}{KIND_LABEL[c.kind]} · {head[:80]} · +{sig.words_added}/−{sig.words_removed} words"
        with st.expander(title):
            st.caption(sig.reason)
            b, a = highlighted(c)
            col_b, col_a = st.columns(2)
            col_b.markdown(f"**Before** ({comp.old.form} filed {comp.old.filed})" +
                           (f" · [open]({c.old.url})" if c.old else ""))
            col_b.markdown(f"<div style='font-size:0.9em'>{b or '<em>not present</em>'}</div>", unsafe_allow_html=True)
            col_a.markdown(f"**After** ({comp.new.form} filed {comp.new.filed})" +
                           (f" · [open]({c.new.url})" if c.new else ""))
            col_a.markdown(f"<div style='font-size:0.9em'>{a or '<em>not present</em>'}</div>", unsafe_allow_html=True)
            if c.note:
                st.caption(c.note)
            review_controls.control(store, key, comp.company, "disclosure", f"{comp.section_title}: {head[:120]}")
        reviews[key] = store.get(key)
    if len(shown) > 60:
        st.caption(f"{len(shown) - 60} more in the download.")
    all_reviews = {r["key"]: (r["status"], r["note"]) for r in store.all(comp.company)}
    st.download_button("Download disclosure changes (Excel)", disclosure_to_excel(comp, all_reviews),
                       f"{comp.company}_{comp.new.accn}_{comp.section_id}_changes.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def selectors(form: str) -> tuple[str, str]:
    c1, c2 = st.columns(2)
    section = c1.selectbox("Section", list(SECTIONS), format_func=lambda s: SECTIONS[s][0])
    bases = ["prior_year"] if form.startswith("10-K") else ["prior_year", "sequential"]
    basis = c2.selectbox("Compare with", bases, format_func=lambda b: "Previous 10-K" if form.startswith("10-K") and b == "prior_year" else BASES[b])
    return section, basis

