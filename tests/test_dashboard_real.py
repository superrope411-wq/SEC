"""The dashboard shows the same numbers as the reconciled pipeline values (real Microsoft data)."""

from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")

ROOT = Path(__file__).resolve().parents[1]
TEN_K = "0000950170-25-100235"


def test_dashboard_matches_reconciled_values(tmp_path, monkeypatch):
    monkeypatch.setenv("EM_MODE", "fixture")
    monkeypatch.setenv("EM_FIXTURE_DIR", str(ROOT / "tests" / "fixtures" / "real"))
    monkeypatch.setenv("EM_DATA_DIR", str(tmp_path))
    at = st_testing.AppTest.from_file(str(ROOT / "app" / "dashboard.py"), default_timeout=300)
    at.run()
    assert not at.exception
    assert any("FIXTURE MODE" in w.value for w in at.warning)
    at.sidebar.selectbox[1].set_value(TEN_K).run()
    at.sidebar.selectbox[2].set_value("annual").run()
    assert not at.exception
    table = at.dataframe[0].value.set_index("Metric")
    # FY2025 vs FY2024 from the 10-K income and cash-flow statements (USD billions, 2 decimals)
    expected = {
        "Revenue": ("281.72", "245.12"),
        "Operating income": ("128.53", "109.43"),
        "Net income": ("101.83", "88.14"),
        "Operating cash flow": ("136.16", "118.55"),
        "Capital expenditures": ("64.55", "44.48"),
        "Free cash flow": ("71.61", "74.07"),
        "Operating margin": ("45.6%", "44.6%"),
    }
    for metric, (cur, pri) in expected.items():
        assert (table.loc[metric, "Current"], table.loc[metric, "Prior"]) == (cur, pri), metric
    assert any("USD billions" in c.value for c in at.caption)
