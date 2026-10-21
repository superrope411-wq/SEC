"""One end-to-end example: "Why did revenue increase in fiscal year 2025?" on Microsoft's FY2025 10-K.

Every step up to the model call runs offline from saved files. With ANTHROPIC_API_KEY set and
--live, the model is called once (or the cached answer reused) and the checked explanation is
appended. Without a key the report says the model step was not run; nothing is simulated.

  EM_MODE=fixture EM_FIXTURE_DIR=tests/fixtures/real python evaluation/m2_example.py [--live]
Writes evaluation/m2/example_revenue_fy2025.md
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from earnings_monitor.analysis import analyze  # noqa: E402
from earnings_monitor.config import COMPANIES, load_settings  # noqa: E402
from earnings_monitor.evidence.retrieve import build_index  # noqa: E402
from earnings_monitor.explain import prompt  # noqa: E402
from earnings_monitor.explain.llm import AiSettings, api_key_present  # noqa: E402
from earnings_monitor.explain.service import generate, prepare  # noqa: E402
from earnings_monitor.explain.store import AiStore  # noqa: E402
from earnings_monitor.pipeline import load_company  # noqa: E402

TEN_K = "0000950170-25-100235"
QUESTION = "Why did revenue increase in fiscal year 2025 compared with fiscal year 2024?"
OUT = ROOT / "evaluation" / "m2" / "example_revenue_fy2025.md"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    settings, ai = load_settings(), AiSettings.from_env()
    t0 = time.monotonic()
    data, _ = load_company(COMPANIES["MSFT"], settings)
    a = analyze(data, TEN_K, "annual")
    t1 = time.monotonic()
    index = build_index(data, TEN_K, settings)
    t2 = time.monotonic()
    prep = prepare(QUESTION, a, index, ai)
    t3 = time.monotonic()
    rev = next(c for c in prep.calc if c.metric_id == "revenue")
    lines = [f"# End-to-end example: {QUESTION}", "",
             f"Filing: {a.filing.form} {a.filing.accn}, filed {a.as_of} ({index.document.url}).",
             f"Data source: {a.data_source}; filing text SHA-256 {index.document.sha256[:16]}…", "",
             "## 1. Calculated change (verified pipeline, Milestone 1)", "",
             f"Revenue {a.current_label}: ${rev.current_value / 1e6:,.0f}M; {a.prior_label}: ${rev.prior_value / 1e6:,.0f}M; "
             f"change ${rev.change_amount / 1e6:,.0f}M ({rev.change_percent * 100:.2f}%).", "",
             f"## 2. Evidence retrieved ({len(prep.hits)} passages of {len(index.passages)} in the filing)", "",
             "| rank | evidence ID | section | page | periods | score | text |", "|---|---|---|---|---|---|---|"]
    for i, h in enumerate(prep.hits, 1):
        p = h.passage
        lines.append(f"| {i} | `{p.evidence_id}` | {p.section} | {p.page} | {', '.join(p.periods)} | {h.score:.1f} | "
                     f"{p.text[:110].replace('|', '/')}… |")
    worst = ai.worst_case_cost(len(prompt.SYSTEM) + len(prep.user))
    lines += ["", "## 3. Model input", "",
              f"Prompt version `{prompt.PROMPT_VERSION}`; {len(prompt.SYSTEM) + len(prep.user):,} characters; "
              f"cache key `{prep.key[:16]}…`; worst-case cost for {ai.model} at max_tokens={ai.max_tokens}: ${worst:.2f}.",
              "", f"Timing: load and analyze {t1 - t0:.2f}s, extract and index the filing {t2 - t1:.2f}s, "
              f"retrieve and build the prompt {t3 - t2:.3f}s.", "", "## 4. Model answer, checked", ""]
    if args.live and api_key_present():
        ex = generate(prep, AiStore(settings.data_dir / "ai_cache.sqlite"), ai)
        lines += [f"Status: **{ex.status}** ({ex.status_reason}); model said: {ex.model_status}.", ""]
        if ex.error:
            lines.append(f"Error: {ex.error}")
        for s in ex.statements:
            lines.append(f"- [{s.kind}, {'accepted' if s.accepted else 'REJECTED'}] {s.text}"
                         + (f" — {'; '.join(s.reasons)}" if s.reasons else ""))
            for c in s.citations:
                if c.citation.quote:
                    lines.append(f"  - `{c.citation.evidence_id}` p.{c.page}: “{c.citation.quote}”")
        for f in ex.figures:
            lines.append(f"- figure {f.figure.stated_text} ({f.figure.metric_id}, {f.figure.measure}): {f.result} {'; '.join(f.reasons)}")
        if ex.usage:
            u = ex.usage
            lines.append(f"\nUsage: {u.model}, {u.input_tokens:,} in / {u.output_tokens:,} out tokens, ${u.cost_usd:.4f}, "
                         f"{u.latency_ms / 1000:.1f}s{' (cached)' if u.cached else ''}.")
    else:
        lines.append("**Not run.** No ANTHROPIC_API_KEY was available (or --live was not given), so no model output "
                     "exists for this example yet. Nothing here is simulated.")
    OUT.write_text("\n".join(lines) + "\n")
    print(OUT.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
