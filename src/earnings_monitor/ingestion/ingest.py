"""Download (or load from fixtures) the two SEC documents milestone 1 needs per company."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from earnings_monitor.config import Company, Settings
from earnings_monitor.ingestion.raw_cache import CachedDocument, RawCache
from earnings_monitor.ingestion.sec_client import COMPANYFACTS_URL, SUBMISSIONS_URL, SecClient

KINDS = {"submissions": SUBMISSIONS_URL, "companyfacts": COMPANYFACTS_URL}


class FixtureMissing(FileNotFoundError):
    pass


@dataclass
class IngestResult:
    company: Company
    documents: dict[str, CachedDocument]
    downloaded: list[str]
    reused: list[str]


def _age(doc: CachedDocument) -> timedelta:
    fetched = datetime.strptime(doc.fetched_at, "%Y%m%dT%H%M%S%fZ").replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - fetched


def ingest_company(
    company: Company,
    settings: Settings,
    refresh: bool = False,
    max_age: timedelta = timedelta(hours=12),
    client: SecClient | None = None,
) -> IngestResult:
    cache = RawCache(settings.raw_dir)
    docs: dict[str, CachedDocument] = {}
    downloaded: list[str] = []
    reused: list[str] = []
    for kind, template in KINDS.items():
        url = template.format(cik10=company.cik10)
        if settings.mode == "fixture":
            docs[kind] = _load_fixture(cache, settings.fixture_dir, kind, company, url)
            reused.append(kind)
            continue
        cached = cache.latest(kind, company.cik10)
        if cached and cached.source == "sec" and not refresh and _age(cached) < max_age:
            docs[kind] = cached
            reused.append(kind)
            continue
        client = client or SecClient(settings.require_user_agent(), settings.max_requests_per_second)
        result = client.get(url)
        docs[kind] = cache.store(kind, company.cik10, url, result.body, source="sec")
        downloaded.append(kind)
    return IngestResult(company, docs, downloaded, reused)


def _load_fixture(cache: RawCache, fixture_dir: Path | None, kind: str, company: Company, url: str) -> CachedDocument:
    if fixture_dir is None:
        raise FixtureMissing("EM_MODE=fixture requires EM_FIXTURE_DIR")
    path = Path(fixture_dir) / kind / f"CIK{company.cik10}.json"
    if not path.exists():
        raise FixtureMissing(
            f"No fixture at {path}. Save the SEC response from {url} there. "
            "Fixture mode never invents data."
        )
    return cache.store(kind, company.cik10, url, path.read_bytes(), source="fixture")
