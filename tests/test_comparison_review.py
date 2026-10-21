"""Cross-company period alignment and review state."""

from datetime import date
from pathlib import Path

import pytest

from earnings_monitor.comparison import align_periods, compare_companies, overlap_days, shared_months
from earnings_monitor.config import COMPANIES, Settings
from earnings_monitor.financial_normalization.calendar import FiscalQuarter
from earnings_monitor.pipeline import load_company
from earnings_monitor.review import ReviewStore, disclosure_key, financial_key

REAL = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "real"


def Q(fy, q, s, e):
    return FiscalQuarter(fy, q, s, e, s, None)


def test_overlap_and_shared_months():
    assert overlap_days(date(2025, 7, 1), date(2025, 9, 30), date(2025, 8, 1), date(2025, 10, 31)) == 61
    assert shared_months(date(2025, 7, 1), date(2025, 9, 30), date(2025, 8, 1), date(2025, 10, 31)) == ["Aug 2025", "Sep 2025"]


def test_alignment_picks_most_overlap_and_warns():
    msft = Q(2026, 1, date(2025, 7, 1), date(2025, 9, 30))
    crm = [Q(2026, 2, date(2025, 5, 1), date(2025, 7, 31)), Q(2026, 3, date(2025, 8, 1), date(2025, 10, 31))]
    al = align_periods("MSFT", msft, {"CRM": crm})
    assert al["CRM"].end == date(2025, 10, 31) and al["CRM"].offset_days == 31
    assert any("31 days after" in w for w in al["CRM"].warnings)
    assert al["MSFT"].warnings == []


def test_53_week_quarter_length_is_flagged():
    anchor = Q(2024, 1, date(2024, 1, 1), date(2024, 3, 31))
    adbe = [Q(2024, 1, date(2023, 12, 2), date(2024, 3, 1))]  # 91 days, ends 30 days early
    long = [Q(2024, 1, date(2023, 11, 25), date(2024, 3, 1))]  # 98 days
    assert not any("days long" in w for w in align_periods("X", anchor, {"A": adbe})["A"].warnings)
    assert any("98 days long" in w for w in align_periods("X", anchor, {"A": long})["A"].warnings)


@pytest.fixture(scope="module")
def datasets(tmp_path_factory):
    s = Settings("fixture", tmp_path_factory.mktemp("cc"), REAL, None, 4)
    return {t: load_company(COMPANIES[t], s)[0] for t in COMPANIES}


def test_real_three_company_quarter(datasets):
    cc = compare_companies(datasets, "MSFT", date(2025, 9, 30))
    cols = {c.ticker: c for c in cc.columns}
    assert cols["CRM"].alignment.label.startswith("FY2026 Q3") and cols["ADBE"].alignment.label.startswith("FY2025 Q3")
    assert cols["ADBE"].alignment.offset_days == -32
    # Each company's own year-over-year revenue growth, from its own filing
    g = cols["CRM"].values["revenue"]
    assert cols["CRM"].filing_accn == "0001108524-25-000238" and abs(g["change"] - (10_259 / 9_444 - 1)) < 1e-6
    assert len([w for w in cc.warnings if "share" in w]) == 2


def test_review_store_roundtrip_and_history(tmp_path):
    s = ReviewStore(tmp_path / "r.sqlite")
    k = financial_key("MSFT", "0000950170-25-100235", "annual", "revenue_growth")
    assert s.get(k) == ("new", "")
    s.set(k, "MSFT", "financial", "Revenue increased", "follow_up", "check Azure")
    s.set(k, "MSFT", "financial", "Revenue increased", "reviewed", "done")
    s.close()
    s = ReviewStore(tmp_path / "r.sqlite")  # survives reopening
    assert s.get(k) == ("reviewed", "done")
    assert [h[1] for h in s.history(k)] == ["follow_up", "reviewed"]
    with pytest.raises(ValueError):
        s.set(k, "MSFT", "financial", "x", "approved")
    assert disclosure_key("A", "n", "o", "mdna", "added", "", "x") != disclosure_key("A", "n", "o", "mdna", "added", "", "y")
