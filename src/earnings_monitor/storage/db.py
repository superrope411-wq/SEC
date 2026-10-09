"""SQLite store for raw-document metadata, original observations, filings and pipeline runs.

Loading is idempotent: a raw document (identified by its SHA-256) is parsed into the
database once per pipeline version. Re-running with unchanged data does no reprocessing.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_documents (
    sha256 TEXT NOT NULL, kind TEXT NOT NULL, cik INTEGER NOT NULL, path TEXT NOT NULL,
    url TEXT NOT NULL, fetched_at TEXT NOT NULL, source TEXT NOT NULL,
    pipeline_version TEXT NOT NULL, loaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (sha256, kind, pipeline_version)
);
CREATE TABLE IF NOT EXISTS observations (
    obs_id TEXT NOT NULL, raw_sha256 TEXT NOT NULL, cik INTEGER NOT NULL, entity TEXT,
    taxonomy TEXT NOT NULL, concept TEXT NOT NULL, concept_label TEXT, unit TEXT NOT NULL,
    value REAL NOT NULL, period_type TEXT NOT NULL, start TEXT, "end" TEXT NOT NULL,
    duration_days INTEGER, accn TEXT NOT NULL, form TEXT, filed TEXT NOT NULL,
    fy INTEGER, fp TEXT, frame TEXT,
    PRIMARY KEY (raw_sha256, obs_id)
);
CREATE INDEX IF NOT EXISTS ix_obs_concept ON observations (cik, concept, "end");
CREATE TABLE IF NOT EXISTS filings (
    cik INTEGER NOT NULL, accn TEXT NOT NULL, form TEXT, filed TEXT, report_date TEXT,
    primary_document TEXT, PRIMARY KEY (cik, accn)
);
CREATE TABLE IF NOT EXISTS companies (
    cik INTEGER PRIMARY KEY, ticker TEXT, name TEXT, fiscal_year_end TEXT
);
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT, cik INTEGER, pipeline_version TEXT,
    mode TEXT, downloaded TEXT, reused TEXT, observations INTEGER, reprocessed INTEGER, seconds REAL
);
"""


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def has_loaded(self, sha256: str, kind: str, pipeline_version: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM raw_documents WHERE sha256=? AND kind=? AND pipeline_version=?",
            (sha256, kind, pipeline_version))
        return cur.fetchone() is not None

    def record_raw(self, sha256, kind, cik, path, url, fetched_at, source, pipeline_version) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO raw_documents (sha256, kind, cik, path, url, fetched_at, source, pipeline_version) "
            "VALUES (?,?,?,?,?,?,?,?)", (sha256, kind, cik, str(path), url, fetched_at, source, pipeline_version))
        self.conn.commit()

    def save_observations(self, obs: pd.DataFrame, raw_sha256: str) -> None:
        df = obs.copy()
        df["raw_sha256"] = raw_sha256
        for c in ("start", "end", "filed"):
            df[c] = df[c].map(lambda d: d.isoformat() if isinstance(d, date) else None)
        cols = list(df.columns)
        placeholders = ",".join("?" * len(cols))
        quoted = ",".join(f'"{c}"' for c in cols)
        self.conn.executemany(
            f"INSERT OR IGNORE INTO observations ({quoted}) VALUES ({placeholders})",
            df.astype(object).where(df.notna(), None).itertuples(index=False, name=None))
        self.conn.commit()

    def load_observations(self, raw_sha256: str) -> pd.DataFrame:
        df = pd.read_sql_query("SELECT * FROM observations WHERE raw_sha256=?", self.conn, params=(raw_sha256,))
        for c in ("start", "end", "filed"):
            df[c] = df[c].map(lambda s: date.fromisoformat(s) if isinstance(s, str) else None).astype(object)
        df["fy"] = df["fy"].astype("Int64")
        df["value"] = df["value"].astype(float)
        return df.drop(columns=["raw_sha256"])

    def save_filings(self, cik: int, filings: pd.DataFrame) -> None:
        rows = [(cik, r.accn, r.form, r.filed.isoformat(),
                 r.report_date.isoformat() if pd.notna(r.report_date) and r.report_date else None,
                 r.primary_document or None) for r in filings.itertuples()]
        self.conn.executemany(
            "INSERT OR REPLACE INTO filings (cik, accn, form, filed, report_date, primary_document) VALUES (?,?,?,?,?,?)",
            rows)
        self.conn.commit()

    def save_company(self, cik, ticker, name, fiscal_year_end) -> None:
        self.conn.execute("INSERT OR REPLACE INTO companies VALUES (?,?,?,?)", (cik, ticker, name, fiscal_year_end))
        self.conn.commit()

    def record_run(self, **kw) -> None:
        cols = ",".join(kw)
        self.conn.execute(f"INSERT INTO pipeline_runs ({cols}) VALUES ({','.join('?' * len(kw))})", tuple(kw.values()))
        self.conn.commit()

    def runs(self) -> pd.DataFrame:
        return pd.read_sql_query("SELECT * FROM pipeline_runs ORDER BY run_id DESC", self.conn)
