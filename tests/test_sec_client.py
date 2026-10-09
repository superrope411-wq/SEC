"""SEC client: identification, throttling, bounded retries, backoff."""

import pytest
import requests

from earnings_monitor.ingestion.sec_client import SecAccessDenied, SecClient, SecError, SecNotFound


class FakeResponse:
    def __init__(self, status, content=b"{}", headers=None):
        self.status_code, self.content, self.headers = status, content, headers or {}


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def make(responses, **kw):
    sleeps = []
    clock = {"t": 0.0}
    c = SecClient("Test User test@example.com", session=FakeSession(responses),
                  sleep=lambda s: sleeps.append(s), clock=lambda: clock["t"], **kw)
    return c, sleeps, clock


def test_requires_contact_email():
    with pytest.raises(ValueError):
        SecClient("no-email-here")


def test_sends_user_agent_header():
    c, _, _ = make([FakeResponse(200, b'{"a":1}')])
    r = c.get("https://data.sec.gov/x")
    assert r.body == b'{"a":1}' and r.attempts == 1
    assert c.session.calls[0][1]["User-Agent"] == "Test User test@example.com"


def test_throttles_to_configured_rate():
    c, sleeps, _ = make([FakeResponse(200), FakeResponse(200)], max_requests_per_second=4)
    c.get("u1")
    c.get("u2")  # clock did not advance, so the second call must wait the full interval
    assert sleeps and abs(sleeps[0] - 0.25) < 1e-9


def test_retries_with_exponential_backoff_then_succeeds():
    c, sleeps, _ = make([FakeResponse(503), FakeResponse(429, headers={"Retry-After": "5"}), FakeResponse(200)],
                        max_requests_per_second=1000)
    r = c.get("u")
    assert r.attempts == 3
    backoffs = [x for x in sleeps if x >= 0.01]  # ignore the tiny throttle waits
    assert backoffs == [1.0, 5.0]  # base backoff, then Retry-After honoured


def test_gives_up_after_max_attempts():
    c, _, _ = make([FakeResponse(500)] * 3, max_attempts=3, max_requests_per_second=1000)
    with pytest.raises(SecError, match="3 attempts"):
        c.get("u")


def test_403_is_not_retried():
    c, _, _ = make([FakeResponse(403), FakeResponse(200)])
    with pytest.raises(SecAccessDenied):
        c.get("u")
    assert len(c.session.calls) == 1


def test_404():
    c, _, _ = make([FakeResponse(404)])
    with pytest.raises(SecNotFound):
        c.get("u")


def test_connection_error_retried():
    c, _, _ = make([requests.ConnectionError("boom"), FakeResponse(200)], max_requests_per_second=1000)
    assert c.get("u").attempts == 2
