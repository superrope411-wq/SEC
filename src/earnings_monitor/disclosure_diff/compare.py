"""Paragraph-level comparison of one section across two filings.

Everything here is deterministic and testable; no model is involved. The steps:

1. Units: the section's paragraphs and bullets (table rows are left to the financial tables).
   Fragments split by a page break (a paragraph ending mid-sentence followed by one starting in
   lower case) are joined first, so a different page layout is not a change.
2. Normalize: case, quotes, dashes, bullets, whitespace and footnote markers.
3. Match, in passes, each matched pair removed from the pool (a pair under the same heading
   needs only REWRITE_THRESHOLD and is labeled "substantially rewritten"):
     a. identical normalized text            -> unchanged (anywhere in the section, so a
                                                 reordered paragraph is not a change)
     b. identical once dates, years, fiscal labels and numbers are masked
                                              -> routine update (numbers are listed separately)
     c. most similar remaining paragraph, word-level similarity >= MATCH_THRESHOLD
                                              -> changed (minor if only a few words differ)
   A paragraph whose text is contained in, or contains, a paragraph of the other filing is a
   split or merge, not an addition or removal.
4. What is left: added (new filing only) and removed (old filing only).

Heading renames are reported separately: paragraphs that are unchanged but sit under a
heading whose text changed.
"""

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Literal

from pydantic import BaseModel, Field

from earnings_monitor.evidence.extract import Passage

MATCH_THRESHOLD = 0.5  # word-sequence similarity needed to call two paragraphs the same paragraph
REWRITE_THRESHOLD = 0.3  # lower bar, only for paragraphs under the same heading: "substantially rewritten"
MINOR_MAX_WORDS = 3  # a changed paragraph with at most this many words changed, and no numbers, is minor
MIN_WORDS = 4  # shorter units (e.g. a stray caption) are ignored
SHINGLE = 5  # words per shingle when checking whether text moved rather than changed
MOVED_COVERAGE = 0.8  # an "added" paragraph whose shingles are 80% in the other filing was moved/regrouped

Kind = Literal["unchanged", "routine_update", "minor_edit", "changed", "added", "removed", "split_or_merge"]

_MONTH = r"(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\.?"
_MASKS = [
    (re.compile(rf"\b{_MONTH}\s+\d{{1,2}},?\s+\d{{4}}\b"), "<date>"),
    (re.compile(rf"\b{_MONTH}\s+\d{{4}}\b"), "<date>"),
    (re.compile(r"\bfiscal (?:year )?\d{4}\b|\bfy ?\d{2,4}\b"), "<fiscal>"),
    (re.compile(r"\b(?:first|second|third|fourth) quarter\b"), "<quarter>"),
    (re.compile(r"\b(?:three|six|nine|twelve) months\b"), "<months>"),
    (re.compile(r"\$?\(?\d[\d,]*(?:\.\d+)?\)?\s*(?:%|percent|billion|million|thousand)?"), "<num>"),
    (re.compile(r"\b(?:19|20)\d{2}\b"), "<year>"),
]
_WORD = re.compile(r"[a-z0-9<>$%.\-']+")


def normalize(text: str) -> str:
    t = text.replace("\xa0", " ").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = t.replace("–", "-").replace("—", "-").replace("​", "")
    t = re.sub(r"^[\s•●▪◦·\-–—*]+", "", t)  # leading bullet
    t = re.sub(r"\(\d\)(?=\s|$)|\[\d+\]", "", t)  # footnote markers like (1) or [2]
    t = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", t, flags=re.I)  # hyphenation: "vertically-integrated" = "vertically integrated"
    return re.sub(r"\s+", " ", t).strip().lower()


def mask(norm: str) -> str:
    t = norm
    for pat, rep in _MASKS:
        t = pat.sub(rep, t)
    return re.sub(r"(?:<num>[\s,]*)+", "<num> ", t).strip()


def words(norm: str) -> list[str]:
    return _WORD.findall(norm)


class Unit(BaseModel):
    """One paragraph (or joined fragments) of a section."""

    text: str
    norm: str
    masked: str
    heading: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    url: str = ""
    page: str | None = None
    position: int = 0


def units(passages: list[Passage], section: str) -> list[Unit]:
    out: list[Unit] = []
    for p in passages:
        if p.section != section or p.kind == "table_row":
            continue
        text = p.text.lstrip("•●▪◦· ").strip()
        prev = out[-1] if out else None
        # Join a fragment split by a page break: previous ends mid-sentence, this one starts in lower case.
        if prev is not None and text and text[0].islower() and not prev.text.rstrip().endswith((".", ":", ";", "?", "!")):
            prev.text = f"{prev.text} {text}"
            prev.evidence_ids.append(p.evidence_id)
            prev.norm = normalize(prev.text)
            prev.masked = mask(prev.norm)
            continue
        n = normalize(text)
        out.append(Unit(text=text, norm=n, masked=mask(n), heading=(p.headings[-1] if p.headings else ""),
                        evidence_ids=[p.evidence_id], url=p.url, page=p.page, position=len(out)))
    return [u for u in out if len(words(u.norm)) >= MIN_WORDS]


class WordOp(BaseModel):
    op: Literal["equal", "insert", "delete", "replace"]
    old: str = ""
    new: str = ""


class Change(BaseModel):
    kind: Kind
    old: Unit | None = None
    new: Unit | None = None
    similarity: float | None = None
    ops: list[WordOp] = Field(default_factory=list)  # word-level diff, for highlighting
    words_changed: int = 0
    numbers_changed: list[tuple[str, str]] = Field(default_factory=list)  # (old, new) number tokens
    novel_words: int = 0  # words of the new text not covered by any 5-word run of the other filing's section
    dropped_words: int = 0  # words of the old text not covered by any 5-word run of the new filing's section
    note: str = ""

    @property
    def is_noise(self) -> bool:
        return self.kind in ("unchanged", "routine_update", "minor_edit", "split_or_merge")


class SectionDiff(BaseModel):
    section: str
    old_count: int
    new_count: int
    changes: list[Change]
    heading_renames: list[tuple[str, str]] = Field(default_factory=list)
    reordered: int = 0  # unchanged paragraphs whose relative order moved

    def counts(self) -> dict[str, int]:
        c = Counter(ch.kind for ch in self.changes)
        return {k: c.get(k, 0) for k in ("added", "removed", "changed", "minor_edit", "routine_update",
                                         "split_or_merge", "unchanged")}

    @property
    def substantive(self) -> list[Change]:
        return [c for c in self.changes if not c.is_noise]


def _word_ops(a: list[str], b: list[str]) -> tuple[list[WordOp], int]:
    sm = SequenceMatcher(None, a, b, autojunk=False)
    ops, changed = [], 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        ops.append(WordOp(op=tag, old=" ".join(a[i1:i2]), new=" ".join(b[j1:j2])))
        if tag != "equal":
            changed += max(i2 - i1, j2 - j1)
    return ops, changed


_NUMTOK = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")


def _numbers(norm: str) -> list[str]:
    return _NUMTOK.findall(norm)


def _shingles(us: list[Unit]) -> set[tuple[str, ...]]:
    out: set[tuple[str, ...]] = set()
    for u in us:
        w = words(u.norm)
        out.update(tuple(w[k:k + SHINGLE]) for k in range(max(1, len(w) - SHINGLE + 1)))
    return out


def _covered(u: Unit, other: set[tuple[str, ...]]) -> list[bool]:
    w = words(u.norm)
    cov = [False] * len(w)
    for k in range(max(1, len(w) - SHINGLE + 1)):
        if tuple(w[k:k + SHINGLE]) in other:
            for x in range(k, min(len(w), k + SHINGLE)):
                cov[x] = True
    return cov


def _coverage(u: Unit, other: set[tuple[str, ...]]) -> float:
    c = _covered(u, other)
    return sum(c) / len(c) if c else 0.0


def _novel(u: Unit, other: set[tuple[str, ...]]) -> int:
    return sum(1 for x in _covered(u, other) if not x)


def compare_units(old: list[Unit], new: list[Unit], section: str = "") -> SectionDiff:
    changes: list[Change] = []
    old_left = dict(enumerate(old))
    new_left = dict(enumerate(new))
    matched_pairs: list[tuple[int, int]] = []

    def take(key):
        index: dict[str, list[int]] = {}
        for i, u in old_left.items():
            index.setdefault(key(u), []).append(i)
        out = []
        for j, u in list(new_left.items()):
            cands = index.get(key(u))
            if cands:
                i = cands.pop(0)
                out.append((i, j))
                del old_left[i], new_left[j]
        return out

    for i, j in take(lambda u: u.norm):
        changes.append(Change(kind="unchanged", old=old[i], new=new[j], similarity=1.0))
        matched_pairs.append((i, j))
    for i, j in take(lambda u: u.masked):
        a, b = old[i], new[j]
        ops, n = _word_ops(words(a.norm), words(b.norm))
        nums = list(zip(_numbers(a.norm), _numbers(b.norm)))
        changes.append(Change(kind="routine_update", old=a, new=b, similarity=1.0, ops=ops, words_changed=n,
                              numbers_changed=[(x, y) for x, y in nums if x != y],
                              note="Only dates, fiscal-period labels or numbers differ."))
        matched_pairs.append((i, j))

    # Similarity matching: best pairs first, prefiltered by shared vocabulary for speed.
    wo = {i: words(u.norm) for i, u in old_left.items()}
    wn = {j: words(u.norm) for j, u in new_left.items()}
    so = {i: set(w) for i, w in wo.items()}
    sn = {j: set(w) for j, w in wn.items()}
    cands = []
    for j in new_left:
        for i in old_left:
            inter = len(so[i] & sn[j])
            if inter == 0 or inter / len(so[i] | sn[j]) < 0.25:
                continue
            r = SequenceMatcher(None, wo[i], wn[j], autojunk=False).ratio()
            same_heading = bool(old_left[i].heading) and old_left[i].heading == new_left[j].heading
            if r >= MATCH_THRESHOLD or (same_heading and r >= REWRITE_THRESHOLD):
                cands.append((r, i, j))
    for r, i, j in sorted(cands, reverse=True):
        if i not in old_left or j not in new_left:
            continue
        a, b = old_left.pop(i), new_left.pop(j)
        ops, n = _word_ops(wo[i], wn[j])
        na, nb = _numbers(a.norm), _numbers(b.norm)
        nums = [(x, y) for x, y in zip(na, nb) if x != y]
        minor = n <= MINOR_MAX_WORDS and na == nb
        changes.append(Change(kind="minor_edit" if minor else "changed", old=a, new=b, similarity=round(r, 3),
                              ops=ops, words_changed=n, numbers_changed=nums,
                              note=f"{n} word(s) differ." if minor else
                              ("Substantially rewritten (same heading, low similarity)." if r < MATCH_THRESHOLD else "")))
        matched_pairs.append((i, j))

    # Splits and merges: leftover text that is (almost all) present elsewhere in the other
    # filing's section, e.g. a bulleted list turned into one paragraph.
    old_sh, new_sh = _shingles(old), _shingles(new)
    for j, u in list(new_left.items()):
        cov = _coverage(u, old_sh)
        if cov >= MOVED_COVERAGE:
            changes.append(Change(kind="split_or_merge", new=u, novel_words=_novel(u, old_sh),
                                  note=f"{cov:.0%} of this text is in the earlier filing, divided or grouped differently."))
        else:
            changes.append(Change(kind="added", new=u, novel_words=_novel(u, old_sh),
                                  note=f"{cov:.0%} of this text appears elsewhere in the earlier filing." if cov >= 0.2 else ""))
    for i, u in list(old_left.items()):
        cov = _coverage(u, new_sh)
        if cov >= MOVED_COVERAGE:
            changes.append(Change(kind="split_or_merge", old=u,
                                  note=f"{cov:.0%} of this text is still in the later filing, divided or grouped differently."))
        else:
            changes.append(Change(kind="removed", old=u, dropped_words=_novel(u, new_sh),
                                  note=f"{cov:.0%} of this text appears elsewhere in the later filing." if cov >= 0.2 else ""))
    for c in changes:
        if c.kind in ("changed", "minor_edit", "routine_update"):
            c.novel_words, c.dropped_words = _novel(c.new, old_sh), _novel(c.old, new_sh)

    # Reordering: unchanged pairs that are out of order relative to each other.
    pairs = sorted(matched_pairs)
    longest = _lis([j for _, j in pairs])
    renames = Counter((old[i].heading, new[j].heading) for i, j in matched_pairs
                      if old[i].heading and new[j].heading and old[i].heading != new[j].heading)
    order = {"added": 0, "removed": 1, "changed": 2, "minor_edit": 3, "routine_update": 4, "split_or_merge": 5, "unchanged": 6}
    changes.sort(key=lambda c: (order[c.kind], (c.new or c.old).position))
    return SectionDiff(section=section, old_count=len(old), new_count=len(new), changes=changes,
                       heading_renames=[k for k, v in renames.items() if v >= 1], reordered=len(pairs) - longest)


def _lis(seq: list[int]) -> int:
    """Length of the longest increasing subsequence (how many matched paragraphs kept their order)."""
    import bisect
    tails: list[int] = []
    for x in seq:
        k = bisect.bisect_left(tails, x)
        if k == len(tails):
            tails.append(x)
        else:
            tails[k] = x
    return len(tails)


def compare_sections(old: list[Passage], new: list[Passage], old_section: str, new_section: str) -> SectionDiff:
    return compare_units(units(old, old_section), units(new, new_section), new_section)
