"""Runtime settings, read from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is optional at runtime
    load_dotenv = None

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


@dataclass(frozen=True)
class Company:
    ticker: str
    cik: int
    name: str

    @property
    def cik10(self) -> str:
        return f"{self.cik:010d}"


# Provisional coverage. CIKs are checked against SEC's submissions API on ingest.
COMPANIES: dict[str, Company] = {
    "MSFT": Company("MSFT", 789019, "Microsoft Corporation"),
    "CRM": Company("CRM", 1108524, "Salesforce, Inc."),
    "ADBE": Company("ADBE", 796343, "Adobe Inc."),
}


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    mode: str  # "live" or "fixture"
    data_dir: Path
    fixture_dir: Path | None
    user_agent: str | None
    max_requests_per_second: float

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "earnings_monitor.sqlite"

    def require_user_agent(self) -> str:
        if not self.user_agent or not _EMAIL.search(self.user_agent):
            raise ConfigError(
                "SEC_USER_AGENT must be set to a name and contact email, e.g. "
                "'Jane Doe jane@example.com'. SEC requires automated clients to identify themselves."
            )
        return self.user_agent


def load_settings(env_file: str | os.PathLike | None = ".env") -> Settings:
    if load_dotenv and env_file and Path(env_file).exists():
        load_dotenv(env_file, override=False)
    mode = os.environ.get("EM_MODE", "live").strip().lower()
    if mode not in {"live", "fixture"}:
        raise ConfigError(f"EM_MODE must be 'live' or 'fixture', got {mode!r}")
    fixture = os.environ.get("EM_FIXTURE_DIR")
    rps = float(os.environ.get("EM_MAX_REQUESTS_PER_SECOND", "4"))
    if not 0 < rps <= 10:
        raise ConfigError("EM_MAX_REQUESTS_PER_SECOND must be in (0, 10]; SEC's limit is 10/s")
    return Settings(
        mode=mode,
        data_dir=Path(os.environ.get("EM_DATA_DIR", "./data")),
        fixture_dir=Path(fixture) if fixture else None,
        user_agent=os.environ.get("SEC_USER_AGENT"),
        max_requests_per_second=rps,
    )
