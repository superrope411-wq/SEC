"""Immutable raw cache: every download is kept as its own file, never overwritten.

Layout: <raw_dir>/<kind>/CIK##########/<UTC timestamp>_<sha256 prefix>.json
A manifest.jsonl beside the files records url, time, size and full hash.
Identical content is not stored twice (the newest manifest entry points to the existing file).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class CachedDocument:
    path: Path
    sha256: str
    fetched_at: str
    url: str
    source: str  # "sec" or "fixture"

    def read_json(self) -> dict:
        return json.loads(self.path.read_bytes())


class RawCache:
    def __init__(self, raw_dir: Path):
        self.raw_dir = Path(raw_dir)

    def _dir(self, kind: str, cik10: str) -> Path:
        return self.raw_dir / kind / f"CIK{cik10}"

    def store(self, kind: str, cik10: str, url: str, body: bytes, source: str = "sec") -> CachedDocument:
        json.loads(body)  # refuse to cache anything that is not valid JSON
        sha = hashlib.sha256(body).hexdigest()
        d = self._dir(kind, cik10)
        d.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        existing = [p for p in d.glob(f"*_{sha[:16]}.json")]
        if existing:
            path = existing[0]
        else:
            path = d / f"{now}_{sha[:16]}.json"
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(body)
            tmp.rename(path)
        entry = {"fetched_at": now, "url": url, "sha256": sha, "bytes": len(body), "file": path.name, "source": source}
        with open(d / "manifest.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        return CachedDocument(path, sha, now, url, source)

    def latest(self, kind: str, cik10: str) -> CachedDocument | None:
        manifest = self._dir(kind, cik10) / "manifest.jsonl"
        if not manifest.exists():
            return None
        lines = [l for l in manifest.read_text(encoding="utf-8").splitlines() if l.strip()]
        if not lines:
            return None
        e = json.loads(lines[-1])
        return CachedDocument(self._dir(kind, cik10) / e["file"], e["sha256"], e["fetched_at"], e["url"], e.get("source", "sec"))
