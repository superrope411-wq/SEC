"""The main HTML document of a filing (the 10-Q or 10-K itself), fetched from EDGAR's archive
or read from saved fixtures, and cached unchanged.

Layout: <data_dir>/raw/filings/CIK##########/<accession>/<document>  (never overwritten)
Fixtures: <fixture_dir>/filings/<accession>/<document>.gz, listed in <fixture_dir>/filings/manifest.json
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from earnings_monitor.config import Company, Settings
from earnings_monitor.models import filing_url


class DocumentUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class FilingDocument:
    accn: str
    document: str
    url: str
    html: bytes
    sha256: str
    source: str  # "sec" or "fixture"


def _fixture(settings: Settings, accn: str, document: str) -> FilingDocument | None:
    if not settings.fixture_dir:
        return None
    path = Path(settings.fixture_dir) / "filings" / accn / f"{document}.gz"
    if not path.exists():
        return None
    html = gzip.decompress(path.read_bytes())
    sha = hashlib.sha256(html).hexdigest()
    manifest = Path(settings.fixture_dir) / "filings" / "manifest.json"
    if manifest.exists():
        listed = {f["path"]: f for f in json.loads(manifest.read_text())["files"]}
        entry = listed.get(f"{accn}/{document}.gz")
        if entry and entry["sha256_uncompressed"] != sha:
            raise DocumentUnavailable(f"Fixture {path} does not match its manifest hash")
    return FilingDocument(accn, document, "", html, sha, "fixture")


def load_document(company: Company, accn: str, document: str, settings: Settings, client=None) -> FilingDocument:
    """Return the filing's main document. Fixture mode never touches the network."""
    url = filing_url(company.cik, accn, document)
    if settings.mode == "fixture":
        doc = _fixture(settings, accn, document)
        if doc is None:
            raise DocumentUnavailable(f"No saved copy of {document} ({accn}) in fixture mode")
        return FilingDocument(doc.accn, doc.document, url, doc.html, doc.sha256, "fixture")
    cached = settings.raw_dir / "filings" / f"CIK{company.cik10}" / accn / document
    if cached.exists():
        html = cached.read_bytes()
        return FilingDocument(accn, document, url, html, hashlib.sha256(html).hexdigest(), "sec")
    if client is None:
        from earnings_monitor.ingestion.sec_client import SecClient
        client = SecClient(settings.require_user_agent(), settings.max_requests_per_second)
    body = client.get(url).body
    cached.parent.mkdir(parents=True, exist_ok=True)
    tmp = cached.with_suffix(".tmp")
    tmp.write_bytes(body)
    tmp.rename(cached)
    sha = hashlib.sha256(body).hexdigest()
    with open(cached.parent / "manifest.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "url": url,
                             "sha256": sha, "bytes": len(body), "file": document}) + "\n")
    return FilingDocument(accn, document, url, body, sha, "sec")
