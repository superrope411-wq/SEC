"""Turn a ModelAnswer into a checked Explanation.

Every statement is kept, but marked accepted or rejected with the reasons, so a reviewer can
see what the model tried to say and why it was not shown as fact. The checks are deterministic:

Management statements (what the filing says):
  1. at least one citation; every evidence ID must resolve to a passage of the analyzed filing;
  2. every quote must appear word for word in its passage (whitespace and quote marks normalized);
  3. every number in the statement must appear in a quote or be a verified figure;
  4. most content words of the statement must appear in the quotes (lexical support), and a
     causal claim ("driven by", "due to") needs causal wording in the quotes themselves;
  5. a number whose figure check failed rejects the statement.
Inferences (what the model concludes):
  1. must name what they are based on; each evidence ID must resolve and each "calc:<metric>"
     must be a calculated metric;
  2. numbers must come from the cited passages or match a calculated value.

The final status is decided here. It is the more cautious of the model's status and the status
the surviving evidence allows (supported < inferred < conflicting evidence < insufficient evidence).
Lexical support is a proxy for entailment, not proof of it; see docs/AI_EXPLANATIONS.md.
"""

from __future__ import annotations

import re

from earnings_monitor.evidence.extract import norm
from earnings_monitor.evidence.retrieve import EvidenceIndex, tokens
from earnings_monitor.evidence.vocab import STOPWORDS
from earnings_monitor.explain.figures import check_figure, mentions
from earnings_monitor.explain.schema import (
    AnswerStatus, CalculatedChange, CheckedStatement, CitationCheck, Explanation, ModelAnswer,
)

RANK = {"supported": 0, "inferred": 1, "conflicting evidence": 2, "insufficient evidence": 3}
MIN_QUOTE = 12
SUPPORT_THRESHOLD = 0.6
_CAUSAL_CLAIM = re.compile(r"\b(because|due to|driven by|drove|driving|as a result of|caused|reflect(?:ed|ing|s)?|attributed|thanks to|led by|primarily from)\b", re.I)
_CAUSAL_TEXT = re.compile(r"\b(driven|due to|because|as a result|primarily|reflect|offset|with growth|impact|attributable|related to|from)\b", re.I)
_NUM = re.compile(r"(?<![A-Za-z])\d[\d,]*(?:\.\d+)?")
_EXTRA_OK = set("company filing management stated state says said report reported according attribute attributed explain explained mainly largely partly part also overall total".split())


def _canon(s: str) -> str:
    return norm(s).lower().replace("“", '"').replace("”", '"')


def quote_in(quote: str, text: str) -> bool:
    q = _canon(quote).strip(" .\"'")
    return len(q) >= min(MIN_QUOTE, len(_canon(text))) and q in _canon(text)


def _numbers(text: str) -> list[str]:
    out = []
    for n in _NUM.findall(text):
        n = n.rstrip(".,").replace(",", "")
        if re.fullmatch(r"(19|20)\d\d", n):  # years are period references, checked elsewhere
            continue
        out.append(n)
    return out


_SAME = {"grew": "increase", "grow": "increase", "growth": "increase", "rose": "increase", "rise": "increase",
         "higher": "increase", "declined": "decrease", "decline": "decrease", "fell": "decrease", "lower": "decrease",
         "drop": "decrease", "dropped": "decrease"}
_CAUSAL_WORDS = {"because", "due", "driven", "drove", "driving", "caused", "result", "primarily", "mainly", "largely"}


def _content(text: str) -> set[str]:
    return {_SAME.get(t, t) for t in tokens(text)
            if t not in STOPWORDS and t not in _EXTRA_OK and t not in _CAUSAL_WORDS and len(t) > 2 and not t[0].isdigit()}


def _calc_mentions_ok(text: str, calc: list[CalculatedChange]) -> list[str]:
    """Numbers in text that match no calculated value."""
    bad = []
    values = []
    for c in calc:
        for v in (c.current_value, c.prior_value, c.change_amount):
            if v is not None:
                values += [v, abs(v)]
                if c.unit != "USD":
                    values += [v * 100, abs(v) * 100]
        if c.change_percent is not None:
            values += [c.change_percent * 100, abs(c.change_percent) * 100]
    for m in mentions(text):
        if not any(abs(abs(m.value) - abs(v)) <= m.tolerance + 1e-9 for v in values):
            bad.append(m.text)
    return bad


def validate(answer: ModelAnswer, index: EvidenceIndex, calc: list[CalculatedChange],
             periods: tuple[str, str], base: Explanation) -> Explanation:
    ex = base.model_copy(deep=True)
    ex.model_status = answer.status
    ex.interpretation = answer.interpretation
    ex.ambiguity = answer.ambiguity
    ex.insufficient_evidence_reason = answer.insufficient_evidence_reason
    ex.unresolved_questions = list(answer.unresolved_questions)
    by_metric = {c.metric_id: c for c in calc}

    ex.figures = [check_figure(f, index.get(f.evidence_id), by_metric.get(f.metric_id), periods) for f in answer.figures]
    failed_numbers = {n for fc in ex.figures if fc.result in ("rejected", "conflict") for n in _numbers(fc.figure.stated_text)}
    verified_numbers = {n for fc in ex.figures if fc.result == "verified" for n in _numbers(fc.figure.stated_text)}

    for s in answer.management_statements:
        cs = CheckedStatement(kind="management", text=s.text, accepted=False)
        quotes = []
        for c in s.citations:
            p = index.get(c.evidence_id)
            found = bool(p) and quote_in(c.quote, p.text)
            cs.citations.append(CitationCheck(citation=c, resolves=p is not None, quote_found=found,
                                              section=p.section if p else None, page=p.page if p else None,
                                              url=p.url if p else None))
            if p is None:
                cs.reasons.append(f"citation {c.evidence_id} does not resolve to a passage of this filing")
            elif not found:
                cs.reasons.append(f"quote not found word for word in {c.evidence_id}")
            else:
                quotes.append(c.quote)
        if not s.citations:
            cs.reasons.append("no citation")
        if quotes and not cs.reasons:
            qtext = " ".join(quotes)
            qnums = set(_numbers(qtext))
            missing = [n for n in _numbers(s.text) if n not in qnums and n not in verified_numbers]
            if missing:
                cs.reasons.append(f"numbers not in the cited quotes: {', '.join(missing)}")
            bad = [n for n in _numbers(s.text) if n in failed_numbers]
            if bad:
                cs.reasons.append(f"numbers that failed the metric/period/unit/value check: {', '.join(bad)}")
            words = _content(s.text)
            covered = words & (_content(qtext) | _content(" ".join(c.metric_label for c in calc)))
            if words and len(covered) / len(words) < SUPPORT_THRESHOLD:
                cs.reasons.append(f"wording not supported by the quotes ({len(covered)}/{len(words)} content words found: "
                                  f"missing {', '.join(sorted(words - covered)[:6])})")
            cause = _CAUSAL_CLAIM.search(s.text)
            if cause and not _CAUSAL_TEXT.search(qtext):
                cs.reasons.append("states a cause, but the quotes give none")
            elif cause:  # the stated cause itself must come from the quotes, word for word
                missing_cause = _content(s.text[cause.end():]) - _content(qtext)
                if missing_cause:
                    cs.reasons.append(f"states a cause the quotes do not give (missing: {', '.join(sorted(missing_cause)[:6])})")
        cs.accepted = bool(quotes) and not cs.reasons
        ex.statements.append(cs)

    for inf in answer.inferences:
        cs = CheckedStatement(kind="inference", text=inf.text, accepted=False, based_on=list(inf.based_on),
                              reasoning=inf.reasoning)
        cited_text = []
        for b in inf.based_on:
            if b.startswith("calc:"):
                if b[5:] not in by_metric:
                    cs.reasons.append(f"{b} is not a calculated metric")
            else:
                p = index.get(b)
                if p is None:
                    cs.reasons.append(f"{b} does not resolve to a passage of this filing")
                else:
                    cited_text.append(p.text)
                    cs.citations.append(CitationCheck(citation={"evidence_id": b, "quote": ""}, resolves=True,
                                                      quote_found=True, section=p.section, page=p.page, url=p.url))
        if not inf.based_on:
            cs.reasons.append("does not say what it is based on")
        src_nums = set(_numbers(" ".join(cited_text))) | verified_numbers
        cited_calc = [by_metric[b[5:]] for b in inf.based_on if b.startswith("calc:") and b[5:] in by_metric]
        stray = [m for m in _calc_mentions_ok(inf.text, cited_calc)
                 if not set(_numbers(m)) <= src_nums]
        if stray:
            cs.reasons.append(f"numbers not in the cited passages or calculations: {', '.join(stray)}")
        cs.accepted = not cs.reasons
        ex.statements.append(cs)

    conflicts = [f for f in ex.figures if f.result == "conflict"]
    if conflicts:
        code_status: AnswerStatus = "conflicting evidence"
        reason = "a number in the filing text disagrees with the verified calculation"
    elif any(s.accepted and s.kind == "management" for s in ex.statements):
        code_status, reason = "supported", "at least one cited management statement passed every check"
    elif any(s.accepted for s in ex.statements):
        code_status, reason = "inferred", "only labeled inferences passed; the filing does not state the reason"
    else:
        code_status, reason = "insufficient evidence", "no statement passed the citation checks"
    final = max(answer.status, code_status, key=lambda s: RANK[s])
    if final != code_status:
        reason = f"the model answered '{answer.status}'; the checks alone would allow '{code_status}'"
    ex.status, ex.status_reason = final, reason
    if final == "insufficient evidence" and not ex.insufficient_evidence_reason:
        ex.insufficient_evidence_reason = reason
    return ex
