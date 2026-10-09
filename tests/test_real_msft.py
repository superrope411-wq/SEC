"""Regression tests on real Microsoft SEC data (cached, unmodified responses in tests/fixtures/real).

Expected values come from evaluation/msft_fy2025_reference.csv, which was typed from the
statement pages of the filings, not produced by this code. See docs/REAL_DATA_VERIFICATION.md.
"""

import csv
import gzip
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from earnings_monitor.analysis import analyze, available_comparisons
from earnings_monitor.config import COMPANIES, Settings
from earnings_monitor.exports.tables import changes_frame, values_frame
from earnings_monitor.financial_normalization.metrics import METRICS
from earnings_monitor.financial_normalization.selection import FactSelector
from earnings_monitor.pipeline import load_company

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "tests" / "fixtures" / "real"
REFERENCE = ROOT / "evaluation" / "msft_fy2025_reference.csv"
MSFT = COMPANIES["MSFT"]
M = 1_000_000
USD_TOL = 500_000  # statements print millions; same tolerance as the reconciliation

FY2025 = {  # accession -> filing date
    "0000950170-24-118967": date(2024, 10, 30),  # 10-Q Q1
    "0000950170-25-010491": date(2025, 1, 29),  # 10-Q Q2
    "0000950170-25-061046": date(2025, 4, 30),  # 10-Q Q3
    "0000950170-25-100235": date(2025, 7, 30),  # 10-K
}
TEN_K = "0000950170-25-100235"


@pytest.fixture(scope="module")
def msft(tmp_path_factory):
    s = Settings("fixture", tmp_path_factory.mktemp("msft"), REAL, None, 4)
    data, _ = load_company(MSFT, s)
    return data


def _reference_rows():
    rows = []
    for r in csv.DictReader(REFERENCE.open()):
        if r["metric_id"] in METRICS and r["metric_id"] not in ("assets", "liabilities_and_equity"):
            rows.append(r)
    return rows


def test_fixture_files_match_manifest():
    manifest = json.loads((REAL / "manifest.json").read_text())
    for f in manifest["files"]:
        raw = gzip.decompress((REAL / f["path"]).read_bytes())
        assert hashlib.sha256(raw).hexdigest() == f["sha256_uncompressed"], f["path"]
        assert f["url"].startswith("https://data.sec.gov/")


def test_fy2025_filings_are_found_with_their_dates(msft):
    for accn, filed in FY2025.items():
        row = msft.filings[msft.filings["accn"] == accn].iloc[0]
        assert row["filed"] == filed
    assert available_comparisons(msft, TEN_K) == ["sequential", "yoy", "annual"]


@pytest.mark.parametrize("r", _reference_rows(), ids=lambda r: f"{r['metric_id']}:{r['period_start']}..{r['period_end']}:{r['accn']}")
def test_reported_values_match_statements(msft, r):
    """Every line item read from the statements is selected correctly as of that filing's date."""
    sel = FactSelector(msft.obs, MSFT, date.fromisoformat(r["filed"]), msft.primary_documents())
    metric = METRICS[r["metric_id"]]
    end = date.fromisoformat(r["period_end"])
    if metric.period_type == "instant":
        v = sel.instant_value(metric, end, str(end))
    else:
        start = date.fromisoformat(r["period_start"])
        direct, notes = sel.select_exact(metric, start, end)
        v = sel._value(metric, "quarter", start, end, str(end), direct, notes)
    assert v.is_available, v.notes
    assert abs(v.value - float(r["value_musd"]) * M) <= USD_TOL
    assert all(s.filed <= date.fromisoformat(r["filed"]) for s in v.sources)


def _value(a, metric_id, start, end):
    return next(v for v in a.all_values if v.metric_id == metric_id and v.period_start == start and v.period_end == end)


def test_q4_is_derived_from_annual_minus_nine_months(msft):
    a = analyze(msft, TEN_K, "sequential")
    q4 = date(2025, 4, 1), date(2025, 6, 30)
    expected = {  # FY2025 10-K minus FY2025 Q3 10-Q nine-month column, in millions
        "revenue": 281_724 - 205_283, "operating_income": 128_528 - 94_205, "net_income": 101_832 - 74_599,
        "operating_cash_flow": 136_162 - 93_515, "capex": 64_551 - 47_472,
    }
    for m, exp in expected.items():
        v = _value(a, m, *q4)
        assert v.status == "derived" and v.value == exp * M, m
        assert {s.accn for s in v.sources} == {TEN_K, "0000950170-25-061046"}
    fcf = _value(a, "free_cash_flow", *q4)
    assert fcf.value == (expected["operating_cash_flow"] - expected["capex"]) * M
    margin = _value(a, "operating_margin", *q4)
    assert margin.value == pytest.approx(expected["operating_income"] / expected["revenue"], abs=1e-9)


def test_standalone_quarter_cash_flow(msft):
    """Q3 operating cash flow equals the statement's three-month column (37,044M), which also
    equals nine months (93,515M) minus six months (56,471M)."""
    a = analyze(msft, "0000950170-25-061046", "yoy")  # Q3: Jan–Mar 2025
    ocf = _value(a, "operating_cash_flow", date(2025, 1, 1), date(2025, 3, 31))
    assert ocf.value == 37_044 * M == (93_515 - 56_471) * M
    if ocf.status == "derived":
        assert sorted(ocf.input_values.values()) == [56_471 * M, 93_515 * M]


def test_every_value_is_available_by_the_filing_date_and_exported(msft):
    for accn, filed in FY2025.items():
        for comp in available_comparisons(msft, accn):
            a = analyze(msft, accn, comp)
            assert a.as_of == filed
            vf, cf = values_frame(a), changes_frame(a)
            for v in a.all_values:
                assert v.is_available, (accn, comp, v.metric_id, v.notes)
                assert v.sources and all(s.filed <= filed for s in v.sources)
            assert vf["Value"].notna().all() and (vf["Sources"].str.len() > 0).all()
            for c in a.changes:
                row = cf[cf["Metric ID"] == c.metric_id].iloc[0]
                assert row["Current value"] == c.current.value and row["Prior value"] == c.prior.value


def test_filings_older_than_the_submissions_list_get_the_right_period(msft):
    """Regression: filings before Oct 2020 come only from companyfacts; their period end was
    taken from cover-page share-count dates (e.g. 2020-07-27) instead of the balance-sheet date."""
    row = msft.filings[msft.filings["accn"] == "0001564590-20-034944"].iloc[0]  # FY2020 10-K
    assert row["report_date"] == date(2020, 6, 30)
    a = analyze(msft, "0001564590-20-034944", "annual")
    rev = next(c for c in a.changes if c.metric_id == "revenue")
    assert rev.current.value == 143_015 * M and rev.prior.value == 125_843 * M


def test_real_retrospective_revision_does_not_leak_backwards(msft):
    """Microsoft early-adopted the ASC 606 revenue standard (full retrospective method) in FY2018,
    an accounting-policy change, not an error correction. FY2017 Q1 revenue was 20,453M in the
    original 10-Q (filed 2016-10-20) and 21,928M as adjusted in the FY2018 Q1 10-Q."""
    q1 = date(2016, 7, 1), date(2016, 9, 30)
    original = analyze(msft, "0001193125-16-742796", "yoy")
    v = _value(original, "revenue", *q1)
    assert v.value == 20_453 * M and not v.restated
    later = analyze(msft, "0001564590-17-020171", "yoy")
    v = _value(later, "revenue", *q1)
    assert v.value == 21_928 * M and v.restated and v.originally_reported == 20_453 * M


def test_real_amendment_is_used(msft):
    """The FY2012 Q2 10-Q/A is the only XBRL source for that quarter in companyfacts."""
    accn = "0001193125-12-026864"
    row = msft.filings[msft.filings["accn"] == accn].iloc[0]
    assert row["form"] == "10-Q/A"
    a = analyze(msft, accn, "yoy")
    v = _value(a, "revenue", date(2011, 10, 1), date(2011, 12, 31))
    assert v.value == 20_885 * M and {s.form for s in v.sources} == {"10-Q/A"}
