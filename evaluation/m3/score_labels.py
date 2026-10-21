"""Score a filled-in label sheet against the tool's verdicts.

Usage: python evaluation/m3/score_labels.py [evaluation/m3/label_sheet.csv]
Precision = share of tool-substantive items labeled S. Noise accuracy = share of tool-noise
items labeled N. Because the two groups were sampled separately, recall over all
differences is estimated by weighting each group by its population size (in label_key.csv).
Items labeled "?" are reported and left out of the rates. Writes evaluation/m3/label_results.md.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    sheet = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "label_sheet.csv"
    labels = {r["item"]: (r["label"].strip().upper(), r["comment"]) for r in csv.DictReader(sheet.open())}
    key = list(csv.DictReader((HERE / "label_key.csv").open()))
    if any(not labels[k["item"]][0] for k in key):
        print("Some items are not labeled yet.")
        return 2
    pop_s, pop_n = int(key[0]["population_substantive"]), int(key[0]["population_noise"])
    groups = {"substantive": [], "noise": []}
    for k in key:
        groups[k["tool_verdict"]].append((k, labels[k["item"]][0]))
    s_lab = [l for _, l in groups["substantive"] if l in ("S", "N")]
    n_lab = [l for _, l in groups["noise"] if l in ("S", "N")]
    precision = s_lab.count("S") / len(s_lab)
    noise_ok = n_lab.count("N") / len(n_lab)
    # estimated number of truly substantive differences in each population
    est_tp = precision * pop_s
    est_fn = (1 - noise_ok) * pop_n
    recall = est_tp / (est_tp + est_fn) if est_tp + est_fn else float("nan")
    unsure = sum(1 for k in key if labels[k["item"]][0] == "?")
    lines = ["# Disclosure changes: labeled sample results", "",
             f"- Tool-substantive items labeled S (precision): {s_lab.count('S')}/{len(s_lab)} = {precision:.0%}",
             f"- Tool-noise items labeled N: {n_lab.count('N')}/{len(n_lab)} = {noise_ok:.0%}",
             f"- Estimated recall over all {pop_s + pop_n} differences (weighted by population): {recall:.0%}",
             f"- Unsure (?) items left out: {unsure}", "", "| Item | Tool | Label | Comment |", "|---|---|---|---|"]
    for k in key:
        lab, com = labels[k["item"]]
        lines.append(f"| {k['item']} | {k['tool_kind']} ({k['tool_verdict']}) | {lab} | {com} |")
    (HERE / "label_results.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
