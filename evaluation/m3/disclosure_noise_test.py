"""Controlled test of the disclosure comparison on real filing text.

For each of the 12 real sections used in Milestone 3 (Risk Factors and MD&A of a 10-K and a
10-Q for each company), take the later filing's section and compare it with a copy that has
  - only formatting noise applied: different whitespace, quotes, dashes and bullet characters;
    20% of paragraphs moved; 10% of paragraphs split across a "page break"; every year
    shifted by one and every other number changed (a routine date/number update); every
    heading renamed;
  - plus known edits: 5 paragraphs inserted (taken from a different company's filing),
    5 deleted, and 5 extended with a new 25-word sentence.
A perfect comparison reports exactly the 15 known edits as substantive and nothing else.
Deterministic (fixed random seed). Offline: reads the saved filings in tests/fixtures/real.

Usage: python evaluation/m3/disclosure_noise_test.py   -> writes evaluation/m3/noise_test.md
"""

from __future__ import annotations

import os
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("EM_MODE", "fixture")
os.environ.setdefault("EM_FIXTURE_DIR", str(ROOT / "tests" / "fixtures" / "real"))
os.environ.setdefault("EM_DATA_DIR", str(ROOT / "data" / "m3"))

from earnings_monitor.config import COMPANIES, load_settings  # noqa: E402
from earnings_monitor.disclosure_diff.compare import Unit, compare_units, join_fragments, mask, normalize, units  # noqa: E402
from earnings_monitor.disclosure_diff.service import SECTIONS  # noqa: E402
from earnings_monitor.evidence.retrieve import build_index  # noqa: E402
from earnings_monitor.pipeline import load_company  # noqa: E402

CASES = [  # (ticker, later filing, form) — the same filings as the real comparisons
    ("MSFT", "0000950170-25-100235", "10-K"), ("MSFT", "0000950170-25-061046", "10-Q"),
    ("CRM", "0001108524-26-000060", "10-K"), ("CRM", "0001108524-25-000088", "10-Q"),
    ("ADBE", "0000796343-26-000003", "10-K"), ("ADBE", "0000796343-25-000073", "10-Q"),
]
DONOR = {"MSFT": "CRM", "CRM": "ADBE", "ADBE": "MSFT"}  # source of "new" paragraphs
NEW_SENTENCE = ("In addition, a newly enacted regulation in a major market requires us to obtain separate customer "
                "consent before processing usage data, which could delay several product launches next year.")


def _unit(text: str, heading: str, pos: int) -> Unit:
    n = normalize(text)
    return Unit(text=text, norm=n, masked=mask(n), heading=heading, position=pos)


def noisy_copy(us: list[Unit], rng: random.Random) -> list[Unit]:
    out: list[Unit] = []
    for u in us:
        t = u.text.replace("'", "’").replace('"', "“").replace(" - ", " — ")
        t = re.sub(r"\b(19|20)(\d\d)\b", lambda m: str(int(m.group(0)) + 1), t)  # every year +1
        t = re.sub(r"(?<![\d.])(\d[\d,]*\.?\d*)(?![\d,])", lambda m: m.group(1).replace("1", "2"), t)  # numbers change
        t = "  ".join(t.split(" "))  # double spaces
        if rng.random() < 0.3:
            t = "• " + t
        heading = (u.heading + " (continued)") if u.heading else ""
        ws = t.split(" ")
        cut = next((k for k in range(len(ws) // 2, len(ws) - 3) if ws[k][:1].islower()), None)
        if rng.random() < 0.10 and cut and len(ws) > 30:  # split across a page break
            out.append(_unit(" ".join(ws[:cut]), heading, len(out)))
            out.append(_unit(" ".join(ws[cut:]), heading, len(out)))
        else:
            out.append(_unit(t, heading, len(out)))
    out = join_fragments(out)  # what units() does with a page break in a real filing
    # move 20% of paragraphs to other positions
    for _ in range(len(out) // 5):
        i, j = rng.randrange(len(out)), rng.randrange(len(out))
        out.insert(j, out.pop(i))
    for k, u in enumerate(out):
        u.position = k
    return out


def run() -> list[dict]:
    settings = load_settings()
    datasets = {t: load_company(COMPANIES[t], settings)[0] for t in COMPANIES}
    donors: dict[tuple[str, str], list[Unit]] = {}
    results = []
    for ticker, accn, form in CASES:
        passages = build_index(datasets[ticker], accn, settings).passages
        for sid, (title, by_form) in SECTIONS.items():
            sec = by_form[form]
            base = units(passages, sec)
            rng = random.Random(f"{ticker}{accn}{sid}")
            noisy = noisy_copy(base, rng)
            noise_only = compare_units(base, noisy, sec)
            # known edits on top of the noise
            key = (DONOR[ticker], sid)
            if key not in donors:
                d_accn = next(a for t, a, f in CASES if t == DONOR[ticker] and f == form)
                donors[key] = units(build_index(datasets[DONOR[ticker]], d_accn, settings).passages, by_form[form])
            edited = list(noisy)
            long = [k for k, u in enumerate(edited) if len(u.norm.split()) >= 40]
            picks = rng.sample(long, 10)
            deleted = picks[:5]
            extended = picks[5:]
            for k in extended:
                u = edited[k]
                edited[k] = _unit(u.text + " " + NEW_SENTENCE, u.heading, u.position)
            inserted = [u for u in rng.sample([u for u in donors[key] if len(u.norm.split()) >= 30], 5)]
            deleted_norms = {edited[k].norm for k in deleted}
            edited = [u for k, u in enumerate(edited) if k not in deleted]
            for u in inserted:
                edited.insert(rng.randrange(len(edited)), _unit(u.text, u.heading, 0))
            for k, u in enumerate(edited):
                u.position = k
            with_edits = compare_units(base, edited, sec)
            sub = with_edits.substantive
            found_ins = sum(1 for c in sub if c.kind == "added" and c.new.norm in {normalize(u.text) for u in inserted})
            found_del = sum(1 for c in sub if c.kind == "removed")
            found_ext = sum(1 for c in sub if c.kind == "changed" and c.new is not None and NEW_SENTENCE.lower()[:60] in c.new.norm)
            results.append({
                "case": f"{ticker} {form} {title}", "paragraphs": len(base),
                "noise_only_substantive": len(noise_only.substantive),
                "noise_only_counts": noise_only.counts(),
                "edits_found": f"{found_ins}/5 inserted, {found_del}/5 deleted, {found_ext}/5 extended",
                "edits_total_found": found_ins + min(found_del, 5) + found_ext,
                "extra_substantive": len(sub) - (found_ins + min(found_del, 5) + found_ext),
                "deleted_texts": len(deleted_norms),
            })
    return results


def main() -> int:
    res = run()
    lines = ["# Disclosure comparison: controlled noise test", "",
             "Generated by `python evaluation/m3/disclosure_noise_test.py` (offline, fixed seed). "
             "See the script's docstring for exactly what is changed.", "",
             "| Section | Paragraphs | Substantive changes reported, noise only (want 0) | Known edits found (want 15/15) | Extra substantive with edits (want 0) |",
             "|---|---|---|---|---|"]
    for r in res:
        lines.append(f"| {r['case']} | {r['paragraphs']} | {r['noise_only_substantive']} | "
                     f"{r['edits_total_found']}/15 ({r['edits_found']}) | {r['extra_substantive']} |")
    tot_par = sum(r["paragraphs"] for r in res)
    tot_noise = sum(r["noise_only_substantive"] for r in res)
    tot_found = sum(r["edits_total_found"] for r in res)
    tot_extra = sum(r["extra_substantive"] for r in res)
    lines += ["", f"**Total:** {tot_par} paragraphs; {tot_noise} false substantive changes from noise alone "
                  f"({tot_noise / tot_par:.1%} of paragraphs); {tot_found}/{15 * len(res)} known edits found; "
                  f"{tot_extra} extra substantive changes when edits were present."]
    (Path(__file__).parent / "noise_test.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
