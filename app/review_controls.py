"""Reviewed / needs-follow-up controls shared by the findings and disclosure panels."""

from __future__ import annotations

import streamlit as st

from earnings_monitor.review import STATUS_LABELS, ReviewStore

ORDER = ["new", "reviewed", "follow_up"]


def control(store: ReviewStore, key: str, company: str, kind: str, title: str) -> str:
    """Render a status selector and note box for one finding; saves on change. Returns the status."""
    status, note = store.get(key)
    c1, c2 = st.columns([1, 2])
    new_status = c1.radio("Review", ORDER, index=ORDER.index(status), format_func=STATUS_LABELS.get,
                          key=f"st|{key}", horizontal=True, label_visibility="collapsed")
    new_note = c2.text_input("Note", value=note, key=f"nt|{key}", placeholder="Note (optional)",
                             label_visibility="collapsed")
    if (new_status, new_note) != (status, note):
        store.set(key, company, kind, title, new_status, new_note)
    return new_status


def badge(status: str) -> str:
    return {"new": "", "reviewed": "✓ ", "follow_up": "⚑ "}[status]
