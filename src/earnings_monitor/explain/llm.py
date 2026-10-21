"""The one model provider, behind a small adapter.

Settings (environment variables; the key is read from the environment only, never stored):
  ANTHROPIC_API_KEY      required for live explanations
  EM_AI_MODEL            default claude-opus-5-5
  EM_AI_EFFORT           low | medium | high (default medium)
  EM_AI_MAX_TOKENS       output limit per call, including thinking (default 16000)
  EM_AI_BUDGET_USD       total spend allowed across all calls recorded in the ledger (default 5.00)
  EM_AI_PRICE_IN / EM_AI_PRICE_OUT   USD per million tokens, to override the built-in prices
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from pydantic import ValidationError

from earnings_monitor.explain.schema import ModelAnswer, Usage

# USD per million tokens: input, output, cache write, cache read. Source: Anthropic model
# documentation for Claude Opus 5.5 ($4 input / $20 output; cache reads $0.20), checked 2026-10-09.
PRICES = {"claude-opus-5-5": (4.0, 20.0, 5.0, 0.20)}


class ModelError(RuntimeError):
    pass


class ModelUnavailable(ModelError):
    """No API key, or the SDK is not installed. Tables and evidence still work."""


class BudgetExceeded(ModelError):
    pass


class ModelRefused(ModelError):
    pass


@dataclass(frozen=True)
class AiSettings:
    model: str = "claude-opus-5-5"
    effort: str = "medium"
    max_tokens: int = 16000
    budget_usd: float = 5.0
    price_in: float | None = None
    price_out: float | None = None

    @classmethod
    def from_env(cls) -> "AiSettings":
        f = lambda k: float(os.environ[k]) if os.environ.get(k) else None
        return cls(model=os.environ.get("EM_AI_MODEL", cls.model),
                   effort=os.environ.get("EM_AI_EFFORT", cls.effort),
                   max_tokens=int(os.environ.get("EM_AI_MAX_TOKENS", cls.max_tokens)),
                   budget_usd=float(os.environ.get("EM_AI_BUDGET_USD", cls.budget_usd)),
                   price_in=f("EM_AI_PRICE_IN"), price_out=f("EM_AI_PRICE_OUT"))

    def prices(self) -> tuple[float, float, float, float]:
        base = PRICES.get(self.model)
        if base is None and (self.price_in is None or self.price_out is None):
            raise ModelError(f"No price known for {self.model}; set EM_AI_PRICE_IN and EM_AI_PRICE_OUT")
        p_in = self.price_in if self.price_in is not None else base[0]
        p_out = self.price_out if self.price_out is not None else base[1]
        cw, cr = (base[2], base[3]) if base else (p_in * 1.25, p_in * 0.1)
        return p_in, p_out, cw, cr

    def cost(self, u: Usage) -> float:
        p_in, p_out, cw, cr = self.prices()
        return (u.input_tokens * p_in + u.output_tokens * p_out + u.cache_creation_input_tokens * cw
                + u.cache_read_input_tokens * cr) / 1e6

    def worst_case_cost(self, prompt_chars: int) -> float:
        p_in, p_out, _, _ = self.prices()
        return (prompt_chars / 3.0 * p_in + self.max_tokens * p_out) / 1e6  # ~3+ chars per token


def answer_schema() -> dict:
    """ModelAnswer as a strict JSON schema: every object closed (additionalProperties false)."""
    schema = ModelAnswer.model_json_schema()

    def close(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            if isinstance(node.get("title"), str):  # schema metadata only; property names are dict keys
                node.pop("title")
            for v in node.values():
                close(v)
        elif isinstance(node, list):
            for v in node:
                close(v)
    close(schema)
    return schema


def api_key_present() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


class ClaudeExplainer:
    def __init__(self, settings: AiSettings, client=None):
        self.settings = settings
        if client is None:
            if not api_key_present():
                raise ModelUnavailable("ANTHROPIC_API_KEY is not set, so explanations cannot be generated. "
                                       "Calculated changes and evidence passages are still shown.")
            try:
                import anthropic
            except ImportError as exc:
                raise ModelUnavailable("The 'anthropic' package is not installed (pip install -e '.[ai]')") from exc
            client = anthropic.Anthropic(max_retries=2, timeout=300.0)
        self.client = client

    def generate(self, system: str, user: str) -> tuple[ModelAnswer, Usage]:
        """One structured-output call. Raises ModelError subclasses; never returns a partial answer."""
        import anthropic

        t0 = time.monotonic()
        try:
            resp = self.client.messages.create(
                model=self.settings.model,
                max_tokens=self.settings.max_tokens,
                thinking={"type": "adaptive"},
                output_config={"effort": self.settings.effort,
                               "format": {"type": "json_schema", "schema": answer_schema()}},
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.AuthenticationError as exc:
            raise ModelUnavailable("The API key was rejected (401). Check ANTHROPIC_API_KEY.") from exc
        except anthropic.RateLimitError as exc:
            raise ModelError("Rate limited by the API (429); try again later.") from exc
        except anthropic.APIStatusError as exc:
            raise ModelError(f"API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ModelError(f"Could not reach the API: {exc}") from exc
        u = resp.usage
        usage = Usage(model=resp.model, input_tokens=u.input_tokens, output_tokens=u.output_tokens,
                      cache_creation_input_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
                      cache_read_input_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
                      latency_ms=int((time.monotonic() - t0) * 1000), stop_reason=resp.stop_reason)
        usage.cost_usd = round(self.settings.cost(usage), 6)
        if resp.stop_reason == "refusal":
            raise _with_usage(ModelRefused("The model declined to answer."), usage)
        if resp.stop_reason == "max_tokens":
            raise _with_usage(ModelError(f"Output hit the {self.settings.max_tokens}-token limit before finishing."), usage)
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            return ModelAnswer.model_validate_json(text), usage
        except ValidationError as exc:
            raise _with_usage(ModelError(f"The model's output did not match the explanation schema: {exc.errors()[:1]}"),
                              usage) from exc


def _with_usage(exc: ModelError, usage: Usage) -> ModelError:
    exc.usage = usage  # failed calls are still billed; the caller records them in the ledger
    return exc
