"""HTTP client for SEC EDGAR with identification, throttling, bounded retries and backoff.

Sources (checked 2026-10-09):
- https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
  ("Please declare your user agent in request headers", "Current max request rate: 10 requests/second")
- https://www.sec.gov/search-filings/edgar-application-programming-interfaces (endpoints, no API key)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable

import requests

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class SecError(RuntimeError):
    pass


class SecAccessDenied(SecError):
    """403: SEC (or a network proxy) refused the request. Retrying will not help."""


class SecNotFound(SecError):
    pass


@dataclass
class FetchResult:
    url: str
    status: int
    body: bytes
    attempts: int


class SecClient:
    def __init__(
        self,
        user_agent: str,
        max_requests_per_second: float = 4.0,
        max_attempts: int = 4,
        backoff_base_seconds: float = 1.0,
        backoff_cap_seconds: float = 30.0,
        timeout_seconds: float = 30.0,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        if not user_agent or "@" not in user_agent:
            raise ValueError("A User-Agent with a contact email is required by SEC")
        self.user_agent = user_agent
        self.min_interval = 1.0 / max_requests_per_second
        self.max_attempts = max_attempts
        self.backoff_base = backoff_base_seconds
        self.backoff_cap = backoff_cap_seconds
        self.timeout = timeout_seconds
        self.session = session or requests.Session()
        self._sleep = sleep
        self._clock = clock
        self._lock = threading.Lock()
        self._last_request: float | None = None

    def _throttle(self) -> None:
        with self._lock:
            now = self._clock()
            if self._last_request is not None:
                wait = self.min_interval - (now - self._last_request)
                if wait > 0:
                    self._sleep(wait)
            self._last_request = self._clock()

    def _backoff(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), self.backoff_cap)
            except ValueError:
                pass
        return min(self.backoff_base * (2 ** (attempt - 1)), self.backoff_cap)

    def get(self, url: str) -> FetchResult:
        headers = {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}
        last_error: str = ""
        for attempt in range(1, self.max_attempts + 1):
            self._throttle()
            try:
                resp = self.session.get(url, headers=headers, timeout=self.timeout)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if "403" in str(exc) and "tunnel" in str(exc).lower():
                    raise SecAccessDenied(
                        f"Network proxy refused the connection to {url}. "
                        "The host must be allowed by this environment's network policy."
                    ) from exc
                if attempt < self.max_attempts:
                    self._sleep(self._backoff(attempt, None))
                continue
            if resp.status_code == 200:
                return FetchResult(url, 200, resp.content, attempt)
            if resp.status_code == 403:
                raise SecAccessDenied(
                    f"403 from {url}. Check SEC_USER_AGENT and request rate; SEC may block "
                    "undeclared or excessive automated traffic."
                )
            if resp.status_code == 404:
                raise SecNotFound(f"404 from {url}")
            last_error = f"HTTP {resp.status_code}"
            if resp.status_code in RETRYABLE_STATUS and attempt < self.max_attempts:
                self._sleep(self._backoff(attempt, resp.headers.get("Retry-After")))
                continue
            if resp.status_code not in RETRYABLE_STATUS:
                break
        raise SecError(f"GET {url} failed after {self.max_attempts} attempts: {last_error}")
