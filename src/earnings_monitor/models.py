"""Typed records that carry provenance from SEC fact to displayed number."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["reported", "derived", "missing", "not_meaningful"]


def filing_url(cik: int, accn: str, primary_document: str | None = None) -> str:
    folder = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}"
    if primary_document:
        return f"{folder}/{primary_document}"
    return f"{folder}/{accn}-index.htm"


class SourceRef(BaseModel):
    """One original XBRL observation used to produce a number."""

    obs_id: str
    taxonomy: str
    concept: str
    unit: str
    value: float
    period_start: date | None
    period_end: date
    accn: str
    form: str
    filed: date
    url: str


class MetricValue(BaseModel):
    """A single number shown to the analyst, with everything needed to verify it."""

    company: str
    cik: int
    metric_id: str
    metric_label: str
    unit: str
    scale: str = "as reported (XBRL values are unscaled)"
    period_type: Literal["duration", "instant"]
    basis: Literal["quarter", "annual", "instant", "ratio"]
    period_start: date | None
    period_end: date
    period_label: str
    value: float | None
    status: Status
    concept: str | None = None
    formula: str | None = None
    input_values: dict[str, float] = Field(default_factory=dict)
    sources: list[SourceRef] = Field(default_factory=list)
    selection_reason: str = ""
    notes: list[str] = Field(default_factory=list)
    restated: bool = False
    originally_reported: float | None = None

    @property
    def is_available(self) -> bool:
        return self.value is not None and self.status in ("reported", "derived")


class Change(BaseModel):
    metric_id: str
    metric_label: str
    unit: str
    comparison: str  # e.g. "Sequential quarter"
    current: MetricValue
    prior: MetricValue
    abs_change: float | None
    pct_change: float | None
    change_kind: Literal["percent", "percentage_points"]
    note: str = ""


class Issue(BaseModel):
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    metric_id: str | None = None
    period_label: str | None = None


class Finding(BaseModel):
    rule_id: str
    title: str
    why: str
    metric_ids: list[str]
    priority: int  # lower = more important; from the rule's configured priority
