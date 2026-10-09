"""Question -> evidence -> (cached or new) model answer -> checked explanation.

Order of work, cheapest first:
  1. scope check (no model): questions about another company or a period after the filing get
     "insufficient evidence" straight away;
  2. retrieval (no model): if nothing in the filing matches, also "insufficient evidence";
  3. cache: an answer for the identical input (prompt version, model, settings, passages,
     calculations, question) is reused at no cost;
  4. model call, only on an explicit request, only within the spending cap;
  5. validation of whatever the model returned (always re-run, also for cached answers).
A failure at step 4 produces an explanation with the error recorded; it never raises into the
dashboard and never affects the financial tables.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from earnings_monitor.analysis import Analysis
from earnings_monitor.config import COMPANIES
from earnings_monitor.evidence.extract import Passage, period_key
from earnings_monitor.evidence.retrieve import EvidenceIndex, Hit
from earnings_monitor.evidence.vocab import COMPANY_NAMES, METRIC_TERMS
from earnings_monitor.explain import prompt
from earnings_monitor.explain.llm import AiSettings, BudgetExceeded, ClaudeExplainer, ModelError
from earnings_monitor.explain.schema import CalculatedChange, Explanation
from earnings_monitor.explain.store import AiStore
from earnings_monitor.explain.validate import validate

TOP_K = 15
MIN_SCORE = 6.0  # below this best retrieval score, nothing in the filing is about the question
# Derived measures are explained through their inputs (Microsoft does not discuss "free cash flow").
COMPONENTS = {"free_cash_flow": ["operating_cash_flow", "capex"], "operating_margin": ["operating_income", "revenue"],
              "net_margin": ["net_income", "revenue"], "cash_conversion": ["operating_cash_flow", "net_income"],
              "total_debt": ["debt_current", "debt_noncurrent"]}


def calculated_changes(a: Analysis) -> list[CalculatedChange]:
    return [CalculatedChange(metric_id=c.metric_id, metric_label=c.metric_label, current_label=c.current.period_label,
                             prior_label=c.prior.period_label, current_value=c.current.value, prior_value=c.prior.value,
                             change_amount=c.abs_change, change_percent=c.pct_change, change_kind=c.change_kind,
                             unit=c.unit) for c in a.changes]


def analysis_periods(a: Analysis) -> tuple[str, str]:
    """Period keys ("12M:2025-06-30") for the current and prior period of the comparison."""
    c = next(c for c in a.changes if c.current.period_start is not None)
    months = lambda v: round(((v.period_end - v.period_start).days + 1) / 30.4)
    return period_key(months(c.current), c.current.period_end), period_key(months(c.prior), c.prior.period_end)


def question_metrics(question: str) -> list[str]:
    q = question.lower()
    found = []
    for mid, terms in METRIC_TERMS.items():
        if any(re.search(rf"(^|[^a-z]){re.escape(t)}([^a-z]|$)", q) for t in terms if t not in ("debt", "net income")) \
                or (mid == "net_income" and "net income" in q):
            found.append(mid)
    for alias, mid in (("sales", "revenue"), ("capex", "capex"), ("cash flow", "operating_cash_flow"),
                       ("margin", "operating_margin"), ("profit", "net_income"), ("earnings", "net_income")):
        if alias in q and mid not in found:
            found.append(mid)
    if "free cash flow" in q:
        found = [m for m in found if m not in ("operating_cash_flow", "free_cash_flow")] + ["free_cash_flow"]
    return found


def scope_check(question: str, a: Analysis) -> str | None:
    q = question.lower()
    for ticker, names in COMPANY_NAMES.items():
        if ticker != a.company.ticker and (any(n in q for n in names) or re.search(rf"\b{ticker.lower()}\b", q)):
            return (f"The question is about {COMPANIES[ticker].name}; this analysis covers only "
                    f"{a.company.name}'s filing {a.filing.accn}.")
    last_year = max(v.period_end.year for v in a.all_values) if a.all_values else a.as_of.year
    years = [int(y) for y in re.findall(r"\b(?:fy\s?|fiscal (?:year )?)?(20\d\d)\b", q)]
    years += [2000 + int(y) for y in re.findall(r"\bfy\s?(\d\d)\b", q)]
    future = [y for y in years if y > last_year]
    if future:
        return (f"The question asks about {', '.join(map(str, sorted(set(future))))}, after the periods in this filing "
                f"(filed {a.as_of}). Filings report results that have happened; they cannot answer that.")
    return None


@dataclass
class Prepared:
    question: str
    analysis: Analysis
    index: EvidenceIndex | None
    calc: list[CalculatedChange]
    periods: tuple[str, str]
    hits: list[Hit]
    gate_reason: str | None
    user: str | None
    key: str | None
    base: Explanation

    @property
    def passages(self) -> list[Passage]:
        return [h.passage for h in self.hits]


def prepare(question: str, a: Analysis, index: EvidenceIndex | None, settings: AiSettings | None = None,
            k: int = TOP_K) -> Prepared:
    settings = settings or AiSettings.from_env()
    calc = calculated_changes(a)
    periods = analysis_periods(a)
    base = Explanation(question=question, company=a.company.ticker, accn=a.filing.accn, comparison=a.comparison,
                       status="insufficient evidence", calculated=calc, prompt_version=prompt.PROMPT_VERSION)
    gate = scope_check(question, a)
    hits: list[Hit] = []
    if index is None:
        gate = gate or "The filing text could not be loaded, so there is no evidence to cite."
    elif not gate:
        metrics = question_metrics(question)
        metrics += [c for m in metrics for c in COMPONENTS.get(m, []) if c not in metrics]
        # Two rankings, interleaved: the question's own words, and the question expanded with the
        # metric's filing vocabulary. The first keeps vague questions ("margins") from being
        # swamped by one metric's wording; the second finds the metric's own MD&A sentence.
        plain = index.search(question, [], periods, k=k)
        expanded = index.search(question, metrics, periods, k=k) if metrics else []
        hits, seen = [], set()
        for pair in zip(expanded or plain, plain):
            for h in pair:
                if h.passage.evidence_id not in seen and len(hits) < k:
                    hits.append(h)
                    seen.add(h.passage.evidence_id)
        for h in plain + expanded:
            if h.passage.evidence_id not in seen and len(hits) < k:
                hits.append(h)
                seen.add(h.passage.evidence_id)
        if not hits or hits[0].score < MIN_SCORE:
            gate = "No passage in the filing matches the question."
    if gate:
        base.status_reason = base.insufficient_evidence_reason = gate
        return Prepared(question, a, index, calc, periods, hits, gate, None, None, base)
    user = prompt.user_message(question, a.company.name, f"{a.filing.form} {a.filing.accn} filed {a.as_of}",
                               a.comparison_label, a.current_label, a.prior_label, calc, [h.passage for h in hits])
    key = prompt.cache_key(settings.model, settings.effort, settings.max_tokens, user)
    base.evidence_ids_offered = [h.passage.evidence_id for h in hits]
    base.cache_key = key
    return Prepared(question, a, index, calc, periods, hits, None, user, key, base)


def from_cache(p: Prepared, store: AiStore) -> Explanation | None:
    if p.gate_reason:
        return p.base
    hit = store.get(p.key)
    if not hit:
        return None
    answer, usage = hit
    ex = validate(answer, p.index, p.calc, p.periods, p.base)
    ex.usage = usage.model_copy(update={"cached": True})
    return ex


def generate(p: Prepared, store: AiStore, settings: AiSettings | None = None, explainer=None) -> Explanation:
    """Explicit, possibly paid step. Uses the cache first; records every API call in the ledger."""
    if p.gate_reason:
        return p.base
    cached = from_cache(p, store)
    if cached:
        return cached
    settings = settings or AiSettings.from_env()
    ex = p.base.model_copy(deep=True)
    try:
        spent = store.spent_usd()
        worst = settings.worst_case_cost(len(prompt.SYSTEM) + len(p.user))
        if spent + worst > settings.budget_usd:
            raise BudgetExceeded(f"Spending cap reached: ${spent:.2f} spent of ${settings.budget_usd:.2f}; this call could "
                                 f"cost up to ${worst:.2f}. Raise EM_AI_BUDGET_USD to continue.")
        explainer = explainer or ClaudeExplainer(settings)
        answer, usage = explainer.generate(prompt.SYSTEM, p.user)
    except ModelError as exc:
        usage = getattr(exc, "usage", None)
        if usage is not None:
            store.log_call(p.key, usage, type(exc).__name__, str(exc))
        ex.error = str(exc)
        ex.usage = usage
        ex.status_reason = f"No explanation: {exc}"
        return ex
    store.put(p.key, prompt.PROMPT_VERSION, p.question, p.analysis.filing.accn, p.analysis.comparison, answer, usage)
    store.log_call(p.key, usage, "ok")
    ex = validate(answer, p.index, p.calc, p.periods, p.base)
    ex.usage = usage
    return ex
