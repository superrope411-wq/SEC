"""Build a company's reference dataset from the face statements of its filings on EDGAR.

Usage: SEC_USER_AGENT="Name email@example.com" python evaluation/verification/build_reference.py CRM
Writes evaluation/verification/<TICKER>_reference.csv. Independent of the pipeline: reads
only EDGAR statement pages (statements.py) and the label specs in companies.py.

Every column of the income and cash-flow statements is kept (current and comparative,
3-month and year-to-date), and both balance-sheet dates, for the filings of the fiscal year
under test and the prior-year filings that their comparisons display. A label that is not printed on a statement (e.g. no current debt that
quarter) produces no row: the reference never assumes a zero that is not printed.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from companies import COMPANIES  # noqa: E402
from statements import Statement, statements  # noqa: E402

OUT = Path(__file__).resolve().parent
FIELDS = ["statement", "accn", "form", "filed", "months", "period_end", "line_item", "metric_id",
          "value_musd", "concept_on_statement", "source_url", "note"]


def _match(label, text: str) -> bool:
    return bool(label.match(text)) if isinstance(label, re.Pattern) else text == label


def find_row(st: Statement, label, region):
    rows = st.rows
    if region:
        start = next((i for i, r in enumerate(rows) if region[0].match(r.label)), None)
        end = next((i for i, r in enumerate(rows) if region[1].match(r.label) and (start is None or i > start)), None)
        if start is None or end is None:
            return None
        rows = rows[start + 1:end]
    return next((r for r in rows if _match(label, r.label)), None)


def build(ticker: str) -> list[dict]:
    c = COMPANIES[ticker]
    out: list[dict] = []
    for accn, form, filed, _ in c["filings"] + c["prior_filings"]:
        sts = statements(c["cik"], accn)
        for metric_id, (kind, label, region) in c["labels"].items():
            st = sts[kind]
            row = find_row(st, label, region)
            if row is None:
                continue
            for (months, end), v in row.values.items():
                if v is None:
                    continue
                note = ""
                if metric_id == "capex":
                    note = f"printed as {v:,.0f} (outflow); stored as positive payment"
                    v = abs(v)
                out.append({"statement": kind, "accn": accn, "form": form, "filed": filed,
                            "months": months, "period_end": end.isoformat(), "line_item": row.label,
                            "metric_id": metric_id, "value_musd": f"{v:g}", "concept_on_statement": row.concept,
                            "source_url": st.url, "note": note})
    return out


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in COMPANIES:
        print(__doc__)
        return 2
    rows = build(sys.argv[1])
    path = OUT / f"{sys.argv[1]}_reference.csv"
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
