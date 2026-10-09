"""Flatten SEC companyfacts JSON into one row per reported fact ("observation").

Every original observation is kept, including duplicates across filings, so the
selection step can explain what it chose and what it passed over.
"""

from __future__ import annotations

import hashlib
from datetime import date

import pandas as pd

OBS_COLUMNS = [
    "obs_id", "cik", "entity", "taxonomy", "concept", "concept_label", "unit", "value",
    "period_type", "start", "end", "duration_days", "accn", "form", "filed", "fy", "fp", "frame",
]

ALLOWED_FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A", "10-KT", "10-KT/A"}


def _obs_id(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def flatten_companyfacts(doc: dict) -> pd.DataFrame:
    cik = int(doc["cik"])
    entity = doc.get("entityName", "")
    rows = []
    for taxonomy, concepts in doc.get("facts", {}).items():
        for concept, body in concepts.items():
            label = body.get("label") or concept
            for unit, facts in body.get("units", {}).items():
                for f in facts:
                    start = f.get("start")
                    end = f["end"]
                    rows.append({
                        "obs_id": _obs_id(taxonomy, concept, unit, start, end, f["val"], f["accn"], f.get("frame")),
                        "cik": cik,
                        "entity": entity,
                        "taxonomy": taxonomy,
                        "concept": concept,
                        "concept_label": label,
                        "unit": unit,
                        "value": f["val"],
                        "period_type": "duration" if start else "instant",
                        "start": date.fromisoformat(start) if start else None,
                        "end": date.fromisoformat(end),
                        "duration_days": (date.fromisoformat(end) - date.fromisoformat(start)).days + 1 if start else None,
                        "accn": f["accn"],
                        "form": f.get("form", ""),
                        "filed": date.fromisoformat(f["filed"]),
                        "fy": f.get("fy"),
                        "fp": f.get("fp"),
                        "frame": f.get("frame"),
                    })
    df = pd.DataFrame(rows, columns=OBS_COLUMNS)
    # The same fact can appear more than once in companyfacts for one filing (e.g. with and
    # without a frame). Those are true duplicates: same concept, unit, period, value, filing.
    df = df.drop_duplicates(subset=["taxonomy", "concept", "unit", "start", "end", "value", "accn"])
    return df.reset_index(drop=True)


def filings_from_submissions(doc: dict) -> pd.DataFrame:
    """Periodic-report filings (10-K/10-Q and amendments) from the submissions API."""
    recent = doc.get("filings", {}).get("recent", {})
    df = pd.DataFrame({
        "accn": recent.get("accessionNumber", []),
        "form": recent.get("form", []),
        "filed": recent.get("filingDate", []),
        "report_date": recent.get("reportDate", []),
        "primary_document": recent.get("primaryDocument", []),
    })
    if df.empty:
        return df
    df = df[df["form"].isin(ALLOWED_FORMS)].copy()
    df["filed"] = pd.to_datetime(df["filed"]).dt.date
    df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce").dt.date
    return df.sort_values("filed", ascending=False).reset_index(drop=True)


def filings_from_facts(obs: pd.DataFrame) -> pd.DataFrame:
    """Fallback filing list when submissions data is unavailable: one row per accession,
    report date = latest period end among that filing's financial-statement (us-gaap) facts.
    Cover-page (dei) facts are excluded: share counts are dated weeks after the period end."""
    o = obs[obs["form"].isin(ALLOWED_FORMS) & (obs["taxonomy"] == "us-gaap")]
    g = o.groupby("accn").agg(form=("form", "first"), filed=("filed", "min"), report_date=("end", "max")).reset_index()
    g["primary_document"] = ""
    return g.sort_values("filed", ascending=False).reset_index(drop=True)
