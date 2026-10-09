"""Filing-text extraction and retrieval on Microsoft's real FY2025 10-Q/10-K documents
(saved unmodified in tests/fixtures/real/filings; no network)."""

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from earnings_monitor.config import COMPANIES, Settings
from earnings_monitor.evidence.documents import DocumentUnavailable, load_document
from earnings_monitor.evidence.extract import extract_passages, find_periods, parse_number
from earnings_monitor.evidence.retrieve import build_index
from earnings_monitor.pipeline import load_company

ROOT = Path(__file__).resolve().parents[1]
FILINGS = ROOT / "tests" / "fixtures" / "real" / "filings"
MSFT = COMPANIES["MSFT"]
TEN_K, Q3 = "0000950170-25-100235", "0000950170-25-061046"
FY25, FY24 = "12M:2025-06-30", "12M:2024-06-30"
FYE = (6, 30)

# Evidence IDs are part of the contract: cached answers and the evaluation set refer to them.
# They must not change unless the filing text (or the section it sits in) changes.
PINNED = {
    "0000950170-25-100235:PII-I7:e21d80cc7e": "Revenue increased $36.6 billion or 15% with growth across each of our segments.",
    "0000950170-25-100235:PII-I7:3453c85d8b": "Total - Revenue: 2025 281,724; 2024 245,122; Percentage Change 15%",
    "0000950170-25-100235:PII-I7:f0a84a2f60": "Cash from operations increased $17.6 billion to $136.2 billion for fiscal year 2025",
    "0000950170-25-061046:PI-I2:650972dfea": "Revenue increased $8.2 billion or 13% with growth across each of our segments.",
    "0000950170-25-061046:PI-I2:f516cfb99a": "Revenue increased $4.6 billion or 21%.",
}


@pytest.fixture(scope="module")
def settings(tmp_path_factory):
    return Settings("fixture", tmp_path_factory.mktemp("ev"), ROOT / "tests" / "fixtures" / "real", None, 4)


@pytest.fixture(scope="module")
def msft(settings):
    data, _ = load_company(MSFT, settings)
    return data


@pytest.fixture(scope="module")
def k_index(msft, settings):
    return build_index(msft, TEN_K, settings)


@pytest.fixture(scope="module")
def q3_index(msft, settings):
    return build_index(msft, Q3, settings)


def test_filing_fixtures_match_manifest():
    manifest = json.loads((FILINGS / "manifest.json").read_text())
    assert len(manifest["files"]) == 4
    for f in manifest["files"]:
        raw = gzip.decompress((FILINGS / f["path"]).read_bytes())
        assert hashlib.sha256(raw).hexdigest() == f["sha256_uncompressed"], f["path"]
        assert f["url"].startswith("https://www.sec.gov/Archives/edgar/data/789019/")


def test_fixture_mode_never_downloads(settings):
    with pytest.raises(DocumentUnavailable):
        load_document(MSFT, "0000950170-99-000000", "missing.htm", settings)


def test_every_fy2025_filing_is_indexed(msft, settings):
    for accn in ("0000950170-24-118967", "0000950170-25-010491", Q3, TEN_K):
        idx = build_index(msft, accn, settings)
        mdna = [p for p in idx.passages if p.is_mdna]
        assert len(mdna) > 100, accn
        assert len(idx.by_id) == len(idx.passages)  # IDs are unique
        assert all(p.evidence_id.startswith(accn + ":") for p in idx.passages)
        assert all(p.page for p in mdna)
        assert idx.document.url.startswith("https://www.sec.gov/Archives/edgar/data/789019/")


def test_evidence_ids_are_stable(k_index, q3_index):
    for eid, text in PINNED.items():
        p = (k_index if eid.startswith(TEN_K) else q3_index).get(eid)
        assert p is not None, eid
        assert p.text.startswith(text)
    again = extract_passages(k_index.document.html, TEN_K, "10-K", k_index.document.url, FYE)
    assert [p.evidence_id for p in again] == [p.evidence_id for p in k_index.passages]


def test_paragraph_context(k_index):
    p = k_index.get("0000950170-25-100235:PII-I7:e21d80cc7e")
    assert (p.section, p.page, p.kind, p.subject) == ("PII-I7", "38", "paragraph", None)
    assert p.periods == [FY25, FY24]  # from the "Fiscal Year 2025 Compared with Fiscal Year 2024" heading
    assert p.url.startswith(k_index.document.url + "#:~:text=Revenue%20increased")


def test_table_row_cells_carry_period_unit_and_scale(k_index):
    p = k_index.get("0000950170-25-100235:PII-I7:3453c85d8b")
    assert (p.row_group, p.row_label, p.table_note) == ("Total", "Revenue", "(In millions, except percentages)")
    cur, pri, pct = p.cells
    assert (cur.value * cur.scale, cur.unit, cur.period) == (281_724e6, "USD", FY25)
    assert (pri.value * pri.scale, pri.period) == (245_122e6, FY24)
    assert (pct.value, pct.unit, pct.period) == (15.0, "percent", None)


def test_segment_paragraph_keeps_its_segment(q3_index):
    p = q3_index.get("0000950170-25-061046:PI-I2:f516cfb99a")
    assert p.subject == "Intelligent Cloud"
    assert p.periods == ["3M:2025-03-31", "3M:2024-03-31"]


def test_nine_month_passages_are_not_tagged_as_the_quarter(q3_index):
    nine = [p for p in q3_index.passages if p.is_mdna and p.text.startswith("Revenue increased $24.9 billion")]
    assert nine and nine[0].periods == ["9M:2025-03-31", "9M:2024-03-31"]


def test_period_and_number_parsing():
    assert find_periods("Three Months Ended March 31, 2025 Compared with Three Months Ended March 31, 2024", FYE) == \
        ["3M:2025-03-31", "3M:2024-03-31"]
    assert find_periods("Highlights from the third quarter of fiscal year 2025 compared with the third quarter of "
                        "fiscal year 2024 included:", FYE) == ["3M:2025-03-31", "3M:2024-03-31"]
    assert find_periods("for fiscal year 2025", FYE) == [FY25]
    assert parse_number("(2,385)") == (-2385.0, "")
    assert parse_number("(5)%") == (-5.0, "%")
    assert parse_number("0ppt") == (0.0, "ppt")
    assert parse_number("Revenue")[0] is None


@pytest.mark.parametrize("accn,query,metrics,periods,expected", [
    (TEN_K, "Why did revenue increase?", ["revenue"], (FY25, FY24), "0000950170-25-100235:PII-I7:e21d80cc7e"),
    (TEN_K, "Why did operating cash flow change?", ["operating_cash_flow"], (FY25, FY24),
     "0000950170-25-100235:PII-I7:f0a84a2f60"),
    (Q3, "Why did revenue change from the same quarter last year?", ["revenue"], ("3M:2025-03-31", "3M:2024-03-31"),
     "0000950170-25-061046:PI-I2:650972dfea"),
])
def test_retrieval_finds_management_explanation(k_index, q3_index, accn, query, metrics, periods, expected):
    idx = k_index if accn == TEN_K else q3_index
    top = [h.passage.evidence_id for h in idx.search(query, metrics, periods, k=5)]
    assert expected in top
