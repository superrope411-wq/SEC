"""Milestone 2 evaluation: evidence-backed explanations for Microsoft FY2025.

Offline (default, free, runs in CI-like conditions):
  - scope check: unanswerable questions about other companies or future periods are stopped
    before any model call;
  - retrieval: every gold quote must be inside a passage offered to the model (recall), since
    the model can only cite what it is given;
  - figure checks on the gold quotes: each dollar and percent change quoted for a pipeline metric
    must pass the metric/period/unit/value check against the verified calculations.

Live (--live, needs ANTHROPIC_API_KEY, costs money, uses the response cache):
  - per question: final status, whether it is allowed, gold citation hit, citation validity,
    rejected statements, tokens, cost and latency.

Usage:
  EM_MODE=fixture EM_FIXTURE_DIR=tests/fixtures/real python evaluation/run_m2_eval.py [--split dev|heldout|all]
  ... python evaluation/run_m2_eval.py --live --split dev
Results are written to evaluation/m2/results_<mode>_<split>.json and .md.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from earnings_monitor.analysis import analyze  # noqa: E402
from earnings_monitor.config import COMPANIES, load_settings  # noqa: E402
from earnings_monitor.evidence.extract import norm  # noqa: E402
from earnings_monitor.evidence.retrieve import build_index  # noqa: E402
from earnings_monitor.explain.figures import check_figure, mentions  # noqa: E402
from earnings_monitor.explain.llm import AiSettings, api_key_present  # noqa: E402
from earnings_monitor.explain.schema import Figure  # noqa: E402
from earnings_monitor.explain.service import generate, prepare, question_metrics  # noqa: E402
from earnings_monitor.explain.store import AiStore  # noqa: E402
from earnings_monitor.pipeline import load_company  # noqa: E402

QUESTIONS = ROOT / "evaluation" / "m2" / "questions.csv"


def canon(s: str) -> str:
    return norm(s).lower().strip(" .")


def gold_figure_checks(prep, gold: list[str]) -> list[dict]:
    """Check each quoted change in a gold sentence about a pipeline metric, as a model figure would be."""
    out = []
    calc_ids = {c.metric_id for c in prep.calc}
    metrics = [m for m in question_metrics(prep.question) if m in calc_ids]
    for g in gold:
        passage = next((h.passage for h in prep.hits if canon(g) in canon(h.passage.text)), None)
        if passage is None:
            continue
        lead = next((m for m in metrics if canon(g).startswith(m.replace("_", " "))), None)
        lead = lead or ("operating_cash_flow" if canon(g).startswith("cash from operations") and "operating_cash_flow" in metrics else None)
        if not lead:
            continue
        sentence = g
        for m in mentions(sentence):
            if m.before.count("$") + m.before.count("%") > 1:  # only the first amount and percent describe the metric
                continue
            measure = "change_percent" if m.unit == "percent" else "change_amount"
            if lead == "operating_cash_flow" and m.before.rstrip().endswith(" to"):
                measure = "current_value"
            fc = check_figure(Figure(metric_id=lead, measure=measure, stated_text=m.text, evidence_id=passage.evidence_id),
                              passage, next(c for c in prep.calc if c.metric_id == lead), prep.periods)
            out.append({"metric": lead, "measure": measure, "text": m.text, "result": fc.result, "reasons": fc.reasons,
                        "expected": fc.expected, "stated": fc.stated})
    return out


def score_live(row: dict, ex, gold: list[str]) -> dict:
    allowed = row["allowed_status"].split("|")
    cits = [c for s in ex.statements if s.kind == "management" for c in s.citations]
    mgmt = [s for s in ex.statements if s.kind == "management"]
    accepted_mgmt = [s for s in mgmt if s.accepted]
    gold_hit = any(any(canon(g) in canon((c.citation.quote or "")) or canon(c.citation.quote) in canon(g)
                       for g in gold) for s in accepted_mgmt for c in s.citations if c.quote_found) if gold else None
    if row["category"] == "supported":
        passed = ex.status in allowed and bool(gold_hit)
    elif row["category"] == "ambiguous":
        passed = ex.status in allowed and bool(ex.ambiguity or ex.unresolved_questions)
    elif row["category"] == "inference_only":  # the filing gives context but not the reason
        passed = ex.status in allowed
    else:
        passed = ex.status in allowed and not accepted_mgmt
    return {"status": ex.status, "model_status": ex.model_status, "allowed": ex.status in allowed, "passed": passed,
            "gold_citation_hit": gold_hit, "citations": len(cits),
            "valid_citations": sum(c.resolves and c.quote_found for c in cits),
            "management_statements": len(mgmt), "rejected_management": len(mgmt) - len(accepted_mgmt),
            "inferences": sum(s.kind == "inference" for s in ex.statements),
            "rejected_inferences": sum(s.kind == "inference" and not s.accepted for s in ex.statements),
            "figures": len(ex.figures), "figures_verified": sum(f.result == "verified" for f in ex.figures),
            "figures_conflict": sum(f.result == "conflict" for f in ex.figures),
            "figures_rejected": sum(f.result == "rejected" for f in ex.figures),
            "ambiguity": ex.ambiguity, "error": ex.error,
            "usage": ex.usage.model_dump() if ex.usage else None,
            "rejections": [{"text": s.text, "reasons": s.reasons} for s in ex.statements if not s.accepted]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="all", choices=["dev", "heldout", "all"])
    ap.add_argument("--live", action="store_true", help="call the model (needs ANTHROPIC_API_KEY; costs money)")
    args = ap.parse_args()
    settings = load_settings()
    ai = AiSettings.from_env()
    if args.live and not api_key_present():
        print("--live needs ANTHROPIC_API_KEY; nothing was run.")
        return 2
    data, _ = load_company(COMPANIES["MSFT"], settings)
    store = AiStore(settings.data_dir / "ai_cache.sqlite")
    rows = [r for r in csv.DictReader(QUESTIONS.open()) if args.split in ("all", r["split"])]
    indexes, results = {}, []
    for r in rows:
        if r["accn"] not in indexes:
            indexes[r["accn"]] = build_index(data, r["accn"], settings)
        a = analyze(data, r["accn"], r["comparison"])
        t0 = time.monotonic()
        prep = prepare(r["question"], a, indexes[r["accn"]], ai)
        gold = [g.strip() for g in r["gold_quotes"].split("||") if g.strip()]
        offered = [h.passage.text for h in prep.hits]
        found = [g for g in gold if any(canon(g) in canon(t) for t in offered)]
        res = {"id": r["id"], "split": r["split"], "category": r["category"], "question": r["question"],
               "gate": prep.gate_reason, "offered": len(prep.hits), "gold": len(gold), "gold_retrieved": len(found),
               "gold_missing": [g for g in gold if g not in found],
               "gold_figure_checks": gold_figure_checks(prep, gold) if not prep.gate_reason else [],
               "prepare_ms": int((time.monotonic() - t0) * 1000)}
        if r["category"] in ("unanswerable", "inference_only") and prep.gate_reason:
            res["offline_pass"] = True
        elif gold:
            res["offline_pass"] = not prep.gate_reason and len(found) == len(gold)
        else:
            res["offline_pass"] = None  # needs the model to decide
        if args.live:
            ex = generate(prep, store, ai)
            res["live"] = score_live(r, ex, gold)
        results.append(res)
        print(f"{r['id']:3} {r['category']:12} gate={'yes' if prep.gate_reason else 'no ':3} "
              f"gold {len(found)}/{len(gold)} offline={res['offline_pass']}"
              + (f" live={res['live']['status']} pass={res['live']['passed']}" if args.live else ""))

    mode = "live" if args.live else "offline"
    out = ROOT / "evaluation" / "m2" / f"results_{mode}_{args.split}.json"
    summary = summarize(results, args.live)
    summary["ai_ledger"] = store.summary() if args.live else None
    out.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "mode": mode, "split": args.split, "model": ai.model if args.live else None,
                               "summary": summary, "results": results}, indent=2, default=str) + "\n")
    out.with_suffix(".md").write_text(markdown(summary, results, mode, args.split))
    print(json.dumps(summary, indent=2))
    return 0


def summarize(results: list[dict], live: bool) -> dict:
    gold = sum(r["gold"] for r in results)
    figs = [f for r in results for f in r["gold_figure_checks"]]
    s = {"questions": len(results),
         "by_category": {c: sum(r["category"] == c for r in results) for c in ("supported", "ambiguous", "unanswerable", "inference_only")},
         "gated_without_model": sum(bool(r["gate"]) for r in results),
         "gold_quote_recall": f"{sum(r['gold_retrieved'] for r in results)}/{gold}",
         "gold_figure_checks": f"{sum(f['result'] == 'verified' for f in figs)}/{len(figs)} verified",
         "offline_pass": f"{sum(r['offline_pass'] is True for r in results)}/{sum(r['offline_pass'] is not None for r in results)}",
         "offline_fail_ids": [r["id"] for r in results if r["offline_pass"] is False]}
    if live:
        lv = [r["live"] for r in results if "live" in r]
        cits = sum(x["citations"] for x in lv)
        mg = sum(x["management_statements"] for x in lv)
        s |= {"live_pass": f"{sum(x['passed'] for x in lv)}/{len(lv)}",
              "live_pass_by_category": {c: f"{sum(r['live']['passed'] for r in results if r['category'] == c and 'live' in r)}/"
                                           f"{sum(r['category'] == c and 'live' in r for r in results)}"
                                        for c in ("supported", "ambiguous", "unanswerable", "inference_only")},
              "citation_validity": f"{sum(x['valid_citations'] for x in lv)}/{cits}",
              "unsupported_claim_rate": f"{sum(x['rejected_management'] for x in lv)}/{mg}",
              "errors": [r["id"] for r in results if r.get("live", {}).get("error")],
              "cost_usd": round(sum((x["usage"] or {}).get("cost_usd", 0) for x in lv if not (x["usage"] or {}).get("cached")), 4),
              "tokens_in": sum((x["usage"] or {}).get("input_tokens", 0) for x in lv),
              "tokens_out": sum((x["usage"] or {}).get("output_tokens", 0) for x in lv),
              "latency_ms_median": sorted((x["usage"] or {}).get("latency_ms", 0) for x in lv)[len(lv) // 2] if lv else None}
    return s


def markdown(summary: dict, results: list[dict], mode: str, split: str) -> str:
    lines = [f"# Milestone 2 evaluation ({mode}, split: {split})", "",
             "Generated by evaluation/run_m2_eval.py. Questions: evaluation/m2/questions.csv.", "", "## Summary", ""]
    lines += [f"- {k}: {v}" for k, v in summary.items() if k != "ai_ledger"]
    lines += ["", "## Per question", "", "| id | category | gate (no model) | gold quotes offered | gold figure checks | offline | live |",
              "|---|---|---|---|---|---|---|"]
    for r in results:
        figs = ", ".join(f"{f['text']} {f['result']}" for f in r["gold_figure_checks"]) or "-"
        live = r.get("live")
        lv = "-" if not live else f"{live['status']} ({'pass' if live['passed'] else 'FAIL'})"
        lines.append(f"| {r['id']} | {r['category']} | {'yes' if r['gate'] else 'no'} | {r['gold_retrieved']}/{r['gold']} | "
                     f"{figs} | {r['offline_pass']} | {lv} |")
    misses = [(r["id"], g) for r in results for g in r["gold_missing"]]
    if misses:
        lines += ["", "## Gold quotes not offered to the model", ""] + [f"- {i}: {g}" for i, g in misses]
    bad = [(r["id"], f) for r in results for f in r["gold_figure_checks"] if f["result"] != "verified"]
    if bad:
        lines += ["", "## Gold figures that failed the check", ""] + [f"- {i}: {f['text']} ({f['measure']}): {'; '.join(f['reasons'])}" for i, f in bad]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
