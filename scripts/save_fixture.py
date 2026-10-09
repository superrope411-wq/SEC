"""Download a company's SEC responses into a fixture folder for offline / test use.

Usage: SEC_USER_AGENT="Name email@example.com" python scripts/save_fixture.py MSFT fixtures/
Fixture files are the unmodified SEC responses; fixture mode is always labeled in the app.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from earnings_monitor.config import COMPANIES, load_settings  # noqa: E402
from earnings_monitor.ingestion.ingest import KINDS  # noqa: E402
from earnings_monitor.ingestion.sec_client import SecClient  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in COMPANIES:
        print(__doc__)
        return 2
    company, out = COMPANIES[sys.argv[1]], Path(sys.argv[2])
    settings = load_settings()
    client = SecClient(settings.require_user_agent(), settings.max_requests_per_second)
    for kind, template in KINDS.items():
        url = template.format(cik10=company.cik10)
        res = client.get(url)
        path = out / kind / f"CIK{company.cik10}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(res.body)
        print(f"saved {url} -> {path} ({len(res.body):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
