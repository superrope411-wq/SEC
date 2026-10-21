"""Response cache and API cost ledger (SQLite, separate from the financial database).

responses: one row per cache key (hash of prompt version, model, settings and the full input),
           holding the validated model answer and the usage of the call that produced it.
calls:     one row per attempted API call, including failures, with tokens, cost and latency.
           Cache hits are not API calls and cost nothing; they are counted separately.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from earnings_monitor.explain.schema import ModelAnswer, Usage

SCHEMA = """
CREATE TABLE IF NOT EXISTS responses (
    cache_key TEXT PRIMARY KEY, created_at TEXT NOT NULL, model TEXT NOT NULL, prompt_version TEXT NOT NULL,
    question TEXT, accn TEXT, comparison TEXT, answer_json TEXT NOT NULL, usage_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, cache_key TEXT, model TEXT, outcome TEXT NOT NULL,
    input_tokens INTEGER, output_tokens INTEGER, cache_creation_input_tokens INTEGER,
    cache_read_input_tokens INTEGER, cost_usd REAL, latency_ms INTEGER, detail TEXT
);
CREATE TABLE IF NOT EXISTS cache_hits (at TEXT NOT NULL, cache_key TEXT NOT NULL);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AiStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def get(self, key: str) -> tuple[ModelAnswer, Usage] | None:
        with self._conn() as c:
            row = c.execute("SELECT answer_json, usage_json FROM responses WHERE cache_key = ?", (key,)).fetchone()
            if row:
                c.execute("INSERT INTO cache_hits VALUES (?, ?)", (_now(), key))
        if not row:
            return None
        return ModelAnswer.model_validate_json(row[0]), Usage.model_validate_json(row[1])

    def put(self, key: str, prompt_version: str, question: str, accn: str, comparison: str,
            answer: ModelAnswer, usage: Usage) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO responses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (key, _now(), usage.model, prompt_version, question, accn, comparison,
                       answer.model_dump_json(), usage.model_dump_json()))

    def log_call(self, key: str | None, usage: Usage, outcome: str, detail: str = "") -> None:
        with self._conn() as c:
            c.execute("INSERT INTO calls (at, cache_key, model, outcome, input_tokens, output_tokens, "
                      "cache_creation_input_tokens, cache_read_input_tokens, cost_usd, latency_ms, detail) "
                      "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (_now(), key, usage.model, outcome, usage.input_tokens, usage.output_tokens,
                       usage.cache_creation_input_tokens, usage.cache_read_input_tokens, usage.cost_usd,
                       usage.latency_ms, detail[:500]))

    def spent_usd(self) -> float:
        with self._conn() as c:
            return float(c.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM calls").fetchone()[0])

    def summary(self) -> dict:
        with self._conn() as c:
            calls = c.execute("SELECT COUNT(*), COALESCE(SUM(cost_usd),0), COALESCE(SUM(input_tokens),0), "
                              "COALESCE(SUM(output_tokens),0), COALESCE(AVG(latency_ms),0) FROM calls").fetchone()
            by_outcome = dict(c.execute("SELECT outcome, COUNT(*) FROM calls GROUP BY outcome").fetchall())
            hits = c.execute("SELECT COUNT(*) FROM cache_hits").fetchone()[0]
            cached = c.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
        return {"api_calls": calls[0], "cost_usd": round(calls[1], 6), "input_tokens": calls[2],
                "output_tokens": calls[3], "avg_latency_ms": round(calls[4]), "outcomes": by_outcome,
                "cache_hits": hits, "cached_answers": cached}

    def recent_calls(self, n: int = 20) -> list[dict]:
        with self._conn() as c:
            c.row_factory = sqlite3.Row
            return [dict(r) for r in c.execute("SELECT * FROM calls ORDER BY id DESC LIMIT ?", (n,))]

    def export(self) -> list[dict]:
        with self._conn() as c:
            c.row_factory = sqlite3.Row
            return [dict(r) | {"answer": json.loads(r["answer_json"])} for r in c.execute("SELECT * FROM responses")]
