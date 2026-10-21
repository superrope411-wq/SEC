"""Structured explanation schema.

Two layers:
- ModelAnswer is what the model must return (validated against this schema by the API's
  structured-output mode and again by pydantic). It holds only cited statements, labeled
  inferences and figures; it never carries calculated numbers of its own.
- Explanation is what the app shows: the calculated changes (straight from the verified
  pipeline), then the model's statements after validation, each marked accepted or rejected
  with the reason, and a final status decided by code, not by the model.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AnswerStatus = Literal["supported", "inferred", "conflicting evidence", "insufficient evidence"]
Measure = Literal["current_value", "prior_value", "change_amount", "change_percent"]


class Citation(BaseModel):
    evidence_id: str = Field(description="ID of a passage given in the prompt, copied exactly")
    quote: str = Field(description="Exact words copied from that passage that support the statement")


class ManagementStatement(BaseModel):
    """Something the filing itself says about why a figure changed."""

    text: str = Field(description="Plain-language restatement of what the filing says")
    citations: list[Citation]


class Inference(BaseModel):
    """A conclusion the filing does not state, drawn from cited passages or calculated changes."""

    text: str
    based_on: list[str] = Field(description="Evidence IDs and/or 'calc:<metric_id>' for calculated changes")
    reasoning: str = Field(description="Why this follows from what it is based on, and what it assumes")


class Figure(BaseModel):
    """A number quoted from a passage, tied to the metric, period and measure it is about."""

    metric_id: str = Field(description="One of the metric IDs in the calculated changes table")
    measure: Measure
    stated_text: str = Field(description="The number exactly as printed in the passage, e.g. '$36.6 billion' or '15%'")
    evidence_id: str


class ModelAnswer(BaseModel):
    status: AnswerStatus
    interpretation: str = Field(description="How the question was understood (metric, period, comparison)")
    ambiguity: str | None = Field(description="If the question could mean more than one thing, what and which reading was used; otherwise null")
    management_statements: list[ManagementStatement]
    inferences: list[Inference]
    figures: list[Figure]
    insufficient_evidence_reason: str | None = Field(description="Required when status is 'insufficient evidence'; otherwise null")
    unresolved_questions: list[str]


class CalculatedChange(BaseModel):
    metric_id: str
    metric_label: str
    current_label: str
    prior_label: str
    current_value: float | None
    prior_value: float | None
    change_amount: float | None
    change_percent: float | None  # fraction, e.g. 0.149
    change_kind: str
    unit: str


class FigureCheck(BaseModel):
    figure: Figure
    result: Literal["verified", "conflict", "rejected", "unchecked"]
    reasons: list[str] = Field(default_factory=list)
    expected: float | None = None
    stated: float | None = None


class CitationCheck(BaseModel):
    citation: Citation
    resolves: bool
    quote_found: bool
    section: str | None = None
    page: str | None = None
    url: str | None = None


class CheckedStatement(BaseModel):
    kind: Literal["management", "inference"]
    text: str
    accepted: bool
    reasons: list[str] = Field(default_factory=list)
    citations: list[CitationCheck] = Field(default_factory=list)
    based_on: list[str] = Field(default_factory=list)
    reasoning: str | None = None


class Usage(BaseModel):
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    cached: bool = False
    stop_reason: str | None = None


class Explanation(BaseModel):
    question: str
    company: str
    accn: str
    comparison: str
    status: AnswerStatus
    model_status: AnswerStatus | None = None
    status_reason: str = ""
    interpretation: str | None = None
    ambiguity: str | None = None
    calculated: list[CalculatedChange] = Field(default_factory=list)
    statements: list[CheckedStatement] = Field(default_factory=list)
    figures: list[FigureCheck] = Field(default_factory=list)
    insufficient_evidence_reason: str | None = None
    unresolved_questions: list[str] = Field(default_factory=list)
    evidence_ids_offered: list[str] = Field(default_factory=list)
    usage: Usage | None = None
    error: str | None = None
    prompt_version: str = ""
    cache_key: str | None = None

    @property
    def accepted(self) -> list[CheckedStatement]:
        return [s for s in self.statements if s.accepted]

    @property
    def rejected(self) -> list[CheckedStatement]:
        return [s for s in self.statements if not s.accepted]
