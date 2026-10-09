"""Keyword and section-aware retrieval over one filing's passages.

Scoring is BM25 over passage text (plus the headings and segment name above it), multiplied by
a section weight (MD&A first, then financial statement notes, risk factors last) and by a
period weight (passages about the analyzed period beat ones about other periods). No
embeddings: every score can be explained from the words that matched.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache

from earnings_monitor.config import Settings
from earnings_monitor.evidence.documents import FilingDocument, load_document
from earnings_monitor.evidence.extract import Passage, extract_passages
from earnings_monitor.evidence.vocab import METRIC_TERMS, STOPWORDS

_TOKEN = re.compile(r"[a-z0-9]+")
_EXPLAINS = re.compile(r"\b(increased|decreased|grew|declined|driven|due to|primarily|offset)\b", re.I)


def tokens(text: str) -> list[str]:
    out = []
    for t in _TOKEN.findall(text.lower()):
        if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        elif len(t) > 5 and t.endswith("eed"):
            pass
        elif len(t) > 5 and t.endswith("ed"):
            t = t[:-1] if t[-3] in "csuvz" else t[:-2]  # increased -> increase, reported -> report
        out.append(t)
    return out


def section_weight(p: Passage) -> float:
    if p.is_mdna:
        return 1.0
    item = p.section.split("-")[-1]
    if (p.form.startswith("10-K") and item == "I8") or (p.form.startswith("10-Q") and p.section == "PI-I1"):
        return 0.6  # financial statements and notes
    if item == "I1A":
        return 0.25  # risk factors: generic, rarely explain a specific period
    if p.section == "COVER":
        return 0.1
    return 0.4


@dataclass
class Hit:
    passage: Passage
    score: float
    matched: list[str] = field(default_factory=list)
    why: str = ""


class EvidenceIndex:
    def __init__(self, passages: list[Passage], document: FilingDocument | None = None):
        self.passages = passages
        self.document = document
        self.by_id = {p.evidence_id: p for p in passages}
        self._docs = [tokens(" ".join([*p.headings, p.subject or "", p.table_title or "", p.text])) for p in passages]
        self._tf = [Counter(d) for d in self._docs]
        self._len = [len(d) for d in self._docs]
        self._avg = sum(self._len) / max(len(self._len), 1)
        df: Counter = Counter()
        for d in self._docs:
            df.update(set(d))
        n = len(passages)
        self._idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def get(self, evidence_id: str) -> Passage | None:
        return self.by_id.get(evidence_id)

    def _bm25(self, i: int, q: list[str]) -> tuple[float, list[str]]:
        k1, b = 1.5, 0.75
        s, matched = 0.0, []
        tf = self._tf[i]
        for t in q:
            f = tf.get(t, 0)
            if not f:
                continue
            matched.append(t)
            s += self._idf.get(t, 0.0) * f * (k1 + 1) / (f + k1 * (1 - b + b * self._len[i] / self._avg))
        return s, matched

    def search(self, query: str, metric_ids: list[str] | tuple = (), periods: list[str] | tuple = (),
               k: int = 12, mdna_only: bool = False) -> list[Hit]:
        q = [t for t in tokens(query) if t not in STOPWORDS]
        phrases = []
        for m in metric_ids:
            phrases += METRIC_TERMS.get(m, [])
        for ph in phrases:
            q += [t for t in tokens(ph) if t not in q]
        if not q:
            return []
        hits = []
        for i, p in enumerate(self.passages):
            if mdna_only and not p.is_mdna:
                continue
            base, matched = self._bm25(i, q)
            if base <= 0:
                continue
            w_sec = section_weight(p)
            if not periods or not p.periods:
                w_per = 0.8 if periods else 1.0
            elif p.periods[0] == periods[0]:
                w_per = 1.3
            elif set(p.periods) & set(periods):
                w_per = 1.0
            else:
                w_per = 0.5
            low = p.text.lower()
            w_phrase = 1.3 if any(re.search(rf"(^|[^a-z]){re.escape(ph)}([^a-z]|$)", low) for ph in phrases) else 1.0
            # A passage that opens with the metric itself ("Revenue increased ...") is the company's
            # own explanation of that metric; one under a segment heading is about the segment.
            w_lead = 1.0
            if any(low.startswith(ph) or low.startswith("total - " + ph) for ph in phrases):
                w_lead = 1.6 if p.subject is None else 1.1
            # Narrative sentences that describe a movement beat bare table rows for "why" questions.
            w_narr = 1.3 if p.kind != "table_row" and _EXPLAINS.search(p.text) else 1.0
            score = base * w_sec * w_per * w_phrase * w_lead * w_narr
            hits.append(Hit(p, score, matched,
                            f"bm25 {base:.2f} x section {w_sec} x period {w_per} x phrase {w_phrase} x lead {w_lead} "
                            f"x narrative {w_narr}"))
        hits.sort(key=lambda h: -h.score)
        return hits[:k]


@lru_cache(maxsize=16)
def _extract_cached(sha256: str, html: bytes, accn: str, form: str, url: str, fye: tuple[int, int]) -> tuple:
    return tuple(extract_passages(html, accn, form, url, fye))


def fiscal_year_end_tuple(mmdd: str | None) -> tuple[int, int]:
    if mmdd and len(mmdd) == 4:
        return int(mmdd[:2]), int(mmdd[2:])
    return 12, 31


def build_index(data, accn: str, settings: Settings, client=None) -> EvidenceIndex:
    """Index the main document of one filing (the as-of filing of an analysis)."""
    row = data.filings[data.filings["accn"] == accn]
    if row.empty:
        raise KeyError(f"Unknown filing {accn}")
    r = row.iloc[0]
    if not r["primary_document"]:
        raise KeyError(f"No primary document recorded for {accn}")
    doc = load_document(data.company, accn, r["primary_document"], settings, client)
    passages = list(_extract_cached(doc.sha256, doc.html, accn, r["form"], doc.url,
                                    fiscal_year_end_tuple(data.fiscal_year_end)))
    return EvidenceIndex(passages, doc)
