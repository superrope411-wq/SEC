import json
from pathlib import Path

import pytest

from earnings_monitor.config import Company, Settings
from earnings_monitor.pipeline import load_company
from tests import synthetic

SYN = Company("SYN", synthetic.CIK, "Synthetic Test Co (not real)")


@pytest.fixture
def fixture_settings(tmp_path: Path) -> Settings:
    facts, subs = synthetic.build()
    fx = tmp_path / "fixtures"
    for kind, doc in (("companyfacts", facts), ("submissions", subs)):
        (fx / kind).mkdir(parents=True)
        (fx / kind / f"CIK{SYN.cik10}.json").write_text(json.dumps(doc))
    return Settings(mode="fixture", data_dir=tmp_path / "data", fixture_dir=fx, user_agent=None,
                    max_requests_per_second=4)


@pytest.fixture
def syn_data(fixture_settings):
    data, _ = load_company(SYN, fixture_settings)
    return data
