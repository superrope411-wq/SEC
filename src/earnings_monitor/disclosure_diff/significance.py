"""Why a disclosure change may matter: transparent keyword rules, not a model.

Each rule looks only at the words that were added or removed (for an added or removed
paragraph, all of its words), and every tag lists the words that triggered it, so an analyst
can see exactly why a change was flagged. Tags describe what the change is about; they do not
say whether it is good or bad, and they are not a substitute for reading the excerpt.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from earnings_monitor.disclosure_diff.compare import Change, words

TOPICS: dict[str, tuple[str, list[str]]] = {
    "legal_regulatory": ("Legal or regulatory matter", [
        r"regulat\w*", r"laws?", r"legislation", r"litigation", r"lawsuits?", r"investigations?", r"settlements?",
        r"antitrust", r"competition authorit\w*", r"fines?", r"penalt\w*", r"enforcement", r"consent decree",
        r"subpoena\w*", r"sanctions?", r"export controls?", r"act"]),
    "ai": ("Artificial intelligence", [r"ai", r"artificial intelligence", r"generative", r"agentic", r"agentforce",
                                       r"copilot", r"firefly", r"models?", r"machine learning", r"gpu\w*"]),
    "cyber": ("Cybersecurity or data privacy", [r"cyber\w*", r"breach\w*", r"hack\w*", r"threat actors?",
                                                 r"nation states?", r"ransomware", r"privacy", r"personal data",
                                                 r"unauthorized access", r"vulnerabilit\w*"]),
    "macro_trade": ("Economy, trade or geopolitics", [r"tariffs?", r"inflation", r"interest rates?", r"recession\w*",
                                                       r"geopolitic\w*", r"war", r"conflicts?", r"trade", r"macroeconomic",
                                                       r"currency", r"foreign exchange"]),
    "deals_capital": ("Acquisitions, debt or capital", [r"acqui\w+", r"merger", r"divest\w*", r"impairment", r"goodwill",
                                                         r"debt", r"notes?", r"borrow\w*", r"credit facility", r"repurchase\w*",
                                                         r"dividends?", r"restructur\w*"]),
    "tax": ("Tax", [r"tax\w*", r"pillar two", r"irs"]),
    "guidance_outlook": ("Outlook language", [r"expect\w*", r"anticipat\w*", r"outlook", r"guidance", r"forecast\w*"]),
}
_COMPILED = {k: (label, re.compile(r"\b(?:" + "|".join(pats) + r")\b")) for k, (label, pats) in TOPICS.items()}


class Tag(BaseModel):
    id: str
    label: str
    triggers: list[str] = Field(default_factory=list)


class Significance(BaseModel):
    tags: list[Tag]
    words_added: int
    words_removed: int
    score: int  # for ordering only: new + dropped words, plus 20 per topic tag, plus 10 for changed numbers
    reason: str


def changed_text(c: Change) -> tuple[str, str]:
    """(added words, removed words) as text."""
    if c.kind == "added":
        return c.new.norm, ""
    if c.kind == "removed":
        return "", c.old.norm
    from earnings_monitor.disclosure_diff.compare import normalize
    return (normalize(" ".join(o.new for o in c.ops if o.op != "equal")),
            normalize(" ".join(o.old for o in c.ops if o.op != "equal")))


def assess(c: Change) -> Significance:
    added, removed = changed_text(c)
    text = f"{added} {removed}"
    tags = []
    for k, (label, pat) in _COMPILED.items():
        hits = sorted(set(m.group(0) for m in pat.finditer(text)))
        if hits:
            tags.append(Tag(id=k, label=label, triggers=hits[:6]))
    if c.numbers_changed:
        tags.append(Tag(id="numbers", label="Figures in the text changed",
                        triggers=[f"{a} → {b}" for a, b in c.numbers_changed[:4]]))
    # Words that are new to the section (not just moved from elsewhere in it) are what count.
    wa, wr = c.novel_words, c.dropped_words
    kind = {"added": "New paragraph", "removed": "Paragraph no longer present", "changed": "Reworded paragraph"}.get(c.kind, c.kind)
    reason = f"{kind}: {wa} word(s) of new language, {wr} word(s) of language dropped"
    if tags:
        reason += "; mentions " + "; ".join(f"{t.label.lower()} ({', '.join(t.triggers)})" for t in tags)
    score = wa + wr + 20 * len([t for t in tags if t.id != "numbers"]) + (10 if c.numbers_changed else 0)
    return Significance(tags=tags, words_added=wa, words_removed=wr, score=score, reason=reason + ".")
