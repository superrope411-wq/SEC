"""Analyst review state for findings: "reviewed" or "needs follow-up", with a note.

Stored in its own SQLite file (<data_dir>/reviews.sqlite) so that rebuilding the facts
database never loses an analyst's work. Every change is also appended to a log, so the
history of a finding's status is kept. Keys are built from what identifies a finding
(company, filing, comparison and rule; or, for a disclosure change, both filings, the
section and a hash of the two texts), not from its position in a list, so they survive a
refresh and re-ranking.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

Status = Literal["new", "reviewed", "follow_up"]
STATUS_LABELS = {"new": "Not reviewed", "reviewed": "Reviewed", "follow_up": "Needs follow-up"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    key TEXT PRIMARY KEY, company TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL,
    status TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL, status TEXT NOT NULL, note TEXT NOT NULL,
    at TEXT NOT NULL
);
"""


def financial_key(ticker: str, accn: str, comparison: str, rule_id: str) -> str:
    return f"fin|{ticker}|{accn}|{comparison}|{rule_id}"


def disclosure_key(ticker: str, new_accn: str, old_accn: str, section: str, kind: str, old_text: str, new_text: str) -> str:
    h = hashlib.sha256(f"{old_text}\x1f{new_text}".encode("utf-8")).hexdigest()[:12]
    return f"disc|{ticker}|{new_accn}|{old_accn}|{section}|{kind}|{h}"


class ReviewStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.executescript(SCHEMA)

    def get(self, key: str) -> tuple[Status, str]:
        row = self.conn.execute("SELECT status, note FROM reviews WHERE key = ?", (key,)).fetchone()
        return (row[0], row[1]) if row else ("new", "")

    def all(self, company: str | None = None) -> list[dict]:
        q = "SELECT key, company, kind, title, status, note, updated_at FROM reviews"
        rows = self.conn.execute(q + (" WHERE company = ?" if company else "") + " ORDER BY updated_at DESC",
                                 (company,) if company else ()).fetchall()
        return [dict(zip(("key", "company", "kind", "title", "status", "note", "updated_at"), r)) for r in rows]

    def set(self, key: str, company: str, kind: str, title: str, status: Status, note: str = "") -> None:
        if status not in STATUS_LABELS:
            raise ValueError(f"Unknown review status {status!r}")
        if self.get(key) == (status, note):
            return
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.conn:
            self.conn.execute(
                "INSERT INTO reviews (key, company, kind, title, status, note, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET status = excluded.status, note = excluded.note, updated_at = excluded.updated_at",
                (key, company, kind, title, status, note, now))
            self.conn.execute("INSERT INTO review_log (key, status, note, at) VALUES (?, ?, ?, ?)", (key, status, note, now))

    def history(self, key: str) -> list[tuple[str, str, str]]:
        return self.conn.execute("SELECT at, status, note FROM review_log WHERE key = ? ORDER BY id", (key,)).fetchall()

    def close(self) -> None:
        self.conn.close()
