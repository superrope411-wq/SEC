"""End-to-end on synthetic fixtures: idempotency, analysis, validation, exports."""

import io
from datetime import date

import pandas as pd
import pytest

from earnings_monitor.analysis import AnalysisError, analyze, available_comparisons
from earnings_monitor.config import Settings
from earnings_monitor.exports.tables import to_csv, to_excel, values_frame
from earnings_monitor.ingestion.ingest import FixtureMissing, ingest_company
from earnings_monitor.pipeline import load_company
from earnings_monitor.storage.db import Store
from tests import synthetic
from tests.conftest import SYN


def test_fixture_mode_never_invents_data(tmp_path):
    s = Settings("fixture", tmp_path / "d", tmp_path / "empty", None, 4)
    with pytest.raises(FixtureMissing):
        ingest_company(SYN, s)


def test_live_mode_requires_user_agent(tmp_path):
    s = Settings("live", tmp_path / "d", None, None, 4)
    with pytest.raises(Exception, match="SEC_USER_AGENT"):
        ingest_company(SYN, s)


def test_ingest_is_idempotent(fixture_settings):
    _, s1 = load_company(SYN, fixture_settings)
    _, s2 = load_company(SYN, fixture_settings)
    assert s1["reprocessed"] is True and s2["reprocessed"] is False
    store = Store(fixture_settings.db_path)
    n = store.conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    assert n == s1["observations"]
    assert len(store.runs()) == 2


def test_yoy_analysis_matches_known_values(syn_data):
    accn = synthetic.accn_for(date(2025, 9, 30))
    a = analyze(syn_data, accn, "yoy")
    by = {c.metric_id: c for c in a.changes}
    assert by["revenue"].current.value == 120_000 and by["revenue"].prior.value == synthetic.RESTATED_FY2025_Q1_REVENUE
    assert by["free_cash_flow"].current.value == 45_000 - 5_000
    assert by["operating_margin"].change_kind == "percentage_points"
    assert a.current_label == "FY2026 Q1 (Jul–Sep 2025)" and a.prior_label == "FY2025 Q1 (Jul–Sep 2024)"
    assert a.filing.url.endswith("/doc12.htm")


def test_sequential_q4_and_annual(syn_data):
    k = synthetic.accn_for(date(2025, 6, 30))
    assert available_comparisons(syn_data, k) == ["sequential", "yoy", "annual"]
    seq = analyze(syn_data, k, "sequential")
    rev = next(c for c in seq.changes if c.metric_id == "revenue")
    assert rev.current.status == "derived" and rev.current.value == synthetic.REVENUE[2025][3]
    ann = analyze(syn_data, k, "annual")
    rev = next(c for c in ann.changes if c.metric_id == "revenue")
    assert rev.current.value == sum(synthetic.REVENUE[2025]) and rev.prior.value == sum(synthetic.REVENUE[2024])


def test_annual_comparison_rejected_for_10q(syn_data):
    with pytest.raises(AnalysisError):
        analyze(syn_data, synthetic.accn_for(date(2025, 9, 30)), "annual")


def test_every_displayed_number_is_traceable(syn_data):
    a = analyze(syn_data, synthetic.accn_for(date(2025, 6, 30)), "sequential")
    for v in a.all_values:
        if v.is_available:
            assert v.sources, v.metric_id
            for s in v.sources:
                assert s.accn and s.filed <= a.as_of and s.url.startswith("https://www.sec.gov/")
            if v.status == "derived":
                assert v.formula and v.input_values


def test_validation_checks_run(syn_data):
    a = analyze(syn_data, synthetic.accn_for(date(2025, 3, 31)), "yoy")
    codes = {i.code for i in a.issues}
    assert "balance_identity_ok" in codes and "ytd_consistent" in codes and "fixture_mode" in codes


def test_exports(syn_data):
    a = analyze(syn_data, synthetic.accn_for(date(2025, 9, 30)), "yoy")
    csv = pd.read_csv(io.BytesIO(to_csv(a)))
    assert "Revenue" in csv["Metric"].values and "Current XBRL concept" in csv.columns
    xlsx = pd.read_excel(io.BytesIO(to_excel(a)), sheet_name=None)
    assert set(xlsx) >= {"Summary", "Changes", "Findings", "Values and sources", "Unresolved issues", "Definitions"}
    assert "LOCAL FIXTURE" in xlsx["Summary"]["Value"].astype(str).str.cat()
    vf = values_frame(a)
    assert vf.loc[vf["Metric"] == "Revenue", "Sources"].str.contains("0000999999").all()
