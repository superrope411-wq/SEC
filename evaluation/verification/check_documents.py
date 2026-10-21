"""Check that every reference figure is printed in the filing's main 10-Q/10-K document.

Usage: SEC_USER_AGENT="Name email@example.com" python evaluation/verification/check_documents.py CRM
The statement pages (R2.htm, ...) are rendered by EDGAR from the filing's XBRL. This is a
second, human-readable source: the HTML document the company filed. Each reference value,
formatted as the company prints it (e.g. 14,339), must appear as a whole number token in
that document. Zeros are skipped (printed as a dash). Exit code 0 only if all are found.
"""

from __future__ import annotations

import csv
import gzip
import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from companies import COMPANIES  # noqa: E402
from statements import fetch, folder  # noqa: E402

SUBMISSIONS = HERE.parents[1] / "tests" / "fixtures" / "real" / "submissions"


def primary_documents(cik: int) -> dict[str, str]:
    recent = json.loads(gzip.decompress((SUBMISSIONS / f"CIK{cik:010d}.json.gz").read_bytes()))["filings"]["recent"]
    return dict(zip(recent["accessionNumber"], recent["primaryDocument"]))


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in COMPANIES:
        print(__doc__)
        return 2
    c = COMPANIES[sys.argv[1]]
    docs = primary_documents(c["cik"])
    rows = list(csv.DictReader((HERE / f"{sys.argv[1]}_reference.csv").open()))
    texts: dict[str, str] = {}
    missing = 0
    for r in rows:
        v = float(r["value_musd"])
        if v == 0:
            continue
        if r["accn"] not in texts:
            raw = fetch(f"{folder(c['cik'], r['accn'])}/{docs[r['accn']]}").decode("utf-8", "ignore")
            texts[r["accn"]] = html.unescape(re.sub(r"<[^>]+>", " ", raw)).replace("\xa0", " ")
        token = f"{abs(v):,.0f}" if v == int(v) else f"{abs(v):,}"
        if not re.search(rf"(?<![\d,.]){re.escape(token)}(?![\d,]|\.\d)", texts[r["accn"]]):
            missing += 1
            print(f"NOT FOUND {r['accn']} {r['metric_id']} {r['months']}M {r['period_end']}: {token}")
    checked = sum(1 for r in rows if float(r["value_musd"]) != 0)
    print(f"{checked} non-zero reference values: {checked - missing} printed in the filing's main document, {missing} not found.")
    return 0 if missing == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
