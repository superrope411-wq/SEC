"""Draw a blinded sample of real disclosure differences for a person to label.

From the 12 real comparisons (Risk Factors and MD&A; 10-K vs previous 10-K and 10-Q vs the same
quarter a year earlier, for each company), take a fixed-seed sample of 40 paragraph pairs:
25 that the tool reports as substantive (added / removed / changed) and 15 that it suppresses
as noise (minor edit / routine update / split or merge). Exact unchanged paragraphs are not
sampled: identical text is not a change by definition.

Writes:
  evaluation/m3/label_sheet.csv   what the labeler sees: before, after, links. No tool output.
  evaluation/m3/label_key.csv     the tool's verdict for each item, kept separate (blinding).
The labeler fills the "label" column: S = substantive (an analyst reviewing this filing would
want to see it), N = not substantive (formatting, routine update, trivial wording), ? = unsure.
Score with evaluation/m3/score_labels.py.
"""

from __future__ import annotations

import csv
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("EM_MODE", "fixture")
os.environ.setdefault("EM_FIXTURE_DIR", str(ROOT / "tests" / "fixtures" / "real"))
os.environ.setdefault("EM_DATA_DIR", str(ROOT / "data" / "m3"))

from earnings_monitor.config import COMPANIES, load_settings  # noqa: E402
from earnings_monitor.disclosure_diff.service import SECTIONS, compare_filings  # noqa: E402
from earnings_monitor.pipeline import load_company  # noqa: E402

HERE = Path(__file__).resolve().parent
CASES = [("MSFT", "0000950170-25-100235"), ("MSFT", "0000950170-25-061046"),
         ("CRM", "0001108524-26-000060"), ("CRM", "0001108524-25-000088"),
         ("ADBE", "0000796343-26-000003"), ("ADBE", "0000796343-25-000073")]
N_SUBSTANTIVE, N_NOISE, SEED = 25, 15, 20261021


def collect() -> tuple[list[dict], dict]:
    settings = load_settings()
    items, totals = [], {"substantive": 0, "noise": 0}
    for ticker, accn in CASES:
        data = load_company(COMPANIES[ticker], settings)[0]
        for sid in SECTIONS:
            comp = compare_filings(data, accn, sid, settings)
            for c in comp.diff.changes:
                if c.kind == "unchanged":
                    continue
                verdict = "noise" if c.is_noise else "substantive"
                totals[verdict] += 1
                items.append({"company": ticker, "section": comp.section_title, "new_form": comp.new.form,
                              "new_filed": str(comp.new.filed), "old_filed": str(comp.old.filed),
                              "new_accn": comp.new.accn, "old_accn": comp.old.accn,
                              "before": c.old.text if c.old else "", "after": c.new.text if c.new else "",
                              "before_link": c.old.url if c.old else "", "after_link": c.new.url if c.new else "",
                              "tool_kind": c.kind, "tool_verdict": verdict})
    return items, totals


def main() -> int:
    items, totals = collect()
    rng = random.Random(SEED)
    sub = rng.sample([i for i in items if i["tool_verdict"] == "substantive"], N_SUBSTANTIVE)
    noise = rng.sample([i for i in items if i["tool_verdict"] == "noise"], N_NOISE)
    sample = sub + noise
    rng.shuffle(sample)
    with (HERE / "label_sheet.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["item", "company", "section", "filing", "compared_with", "before", "after", "before_link",
                    "after_link", "label", "comment"])
        for k, i in enumerate(sample, start=1):
            w.writerow([k, i["company"], i["section"], f"{i['new_form']} filed {i['new_filed']}", f"filed {i['old_filed']}",
                        i["before"] or "(not present)", i["after"] or "(not present)", i["before_link"], i["after_link"], "", ""])
    with (HERE / "label_key.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["item", "tool_kind", "tool_verdict", "population_substantive", "population_noise"])
        for k, i in enumerate(sample, start=1):
            w.writerow([k, i["tool_kind"], i["tool_verdict"], totals["substantive"], totals["noise"]])
    print(f"population: {totals}; wrote {len(sample)} items to {HERE / 'label_sheet.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
