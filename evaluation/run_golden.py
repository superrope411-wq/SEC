"""Compare the pipeline against evaluation/golden_set.csv and print a scorecard.

Usage: python evaluation/run_golden.py [path/to/golden_set.csv]
Every row names a filing (accn), a comparison, a metric and which side ("current" or
"prior") to check. The script reports matches within tolerance; it never edits the CSV.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earnings_monitor.analysis import analyze  # noqa: E402
from earnings_monitor.config import COMPANIES, load_settings  # noqa: E402
from earnings_monitor.pipeline import load_company  # noqa: E402


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("golden_set.csv"))
    rows = [r for r in csv.DictReader(l for l in path.read_text().splitlines() if not l.startswith("#")) if r.get("ticker")]
    if not rows:
        print(f"{path} has no cases yet. Add hand-checked rows first.")
        return 1
    settings = load_settings()
    cache: dict = {}
    ok = fail = 0
    t0 = time.perf_counter()
    for r in rows:
        key = r["ticker"]
        if key not in cache:
            cache[key] = load_company(COMPANIES[key], settings)[0]
        a = analyze(cache[key], r["accn"], r["comparison"])
        ch = next((c for c in a.changes if c.metric_id == r["metric_id"]), None)
        v = None if ch is None else (ch.current if r["period"] == "current" else ch.prior)
        exp_status = r.get("expected_status") or "reported"
        if v is None:
            verdict, detail = False, "metric not in analysis"
        elif r["expected_value"] == "":
            verdict, detail = v.status == exp_status, f"status {v.status}"
        else:
            exp, tol = float(r["expected_value"]), float(r.get("tolerance_abs") or 0)
            verdict = v.value is not None and abs(v.value - exp) <= tol and v.status in ("reported", "derived")
            detail = f"got {v.value} ({v.status}), expected {exp} ±{tol}"
        ok += verdict
        fail += not verdict
        print(f"{'PASS' if verdict else 'FAIL'}  {r['ticker']} {r['accn']} {r['comparison']} {r['metric_id']}/{r['period']}: {detail}")
    print(f"\n{ok} passed, {fail} failed, {len(rows)} total, {time.perf_counter() - t0:.1f}s")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
