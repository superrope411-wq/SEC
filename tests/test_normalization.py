"""Period normalization and fact selection against synthetic data with known answers."""

from datetime import date


from earnings_monitor.financial_normalization.metrics import METRICS
from earnings_monitor.financial_normalization.selection import FactSelector
from tests import synthetic


def test_calendar_detects_june_fiscal_year(syn_data):
    years = {y.fiscal_year: (y.start, y.end) for y in syn_data.calendar.years}
    assert years[2025] == (date(2024, 7, 1), date(2025, 6, 30))
    assert syn_data.fiscal_year_end == "0630"


def test_calendar_quarters_use_company_fiscal_labels(syn_data):
    q = syn_data.calendar.quarter_ending(date(2024, 12, 31))
    assert q.label == "FY2025 Q2"
    assert q.long_label == "FY2025 Q2 (Oct–Dec 2024)"
    assert (q.start, q.end) == (date(2024, 10, 1), date(2024, 12, 31))


def test_open_fiscal_year_gets_quarters(syn_data):
    q = syn_data.calendar.quarter_ending(date(2025, 9, 30))
    assert q.label == "FY2026 Q1" and q.fy_end is None


def test_duplicate_fact_within_filing_is_collapsed(syn_data):
    ni = syn_data.obs[(syn_data.obs["concept"] == "NetIncomeLoss") & (syn_data.obs["end"] == date(2022, 9, 30))]
    assert ni["accn"].value_counts().max() == 1


def _selector(data, as_of):
    return FactSelector(data.obs, data.company, as_of, data.primary_documents())


def test_three_month_fact_is_reported_directly(syn_data):
    cal = syn_data.calendar
    q = cal.quarter_ending(date(2024, 12, 31))
    v = _selector(syn_data, date(2026, 1, 1)).quarter_value(METRICS["revenue"], q, cal)
    assert v.status == "reported" and v.value == synthetic.REVENUE[2025][1]
    assert v.concept == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert len(v.sources) == 1 and v.sources[0].url.startswith("https://www.sec.gov/Archives/edgar/data/999999/")


def test_cash_flow_quarter_is_derived_from_ytd(syn_data):
    cal = syn_data.calendar
    q = cal.quarter_ending(date(2025, 3, 31))  # FY2025 Q3
    v = _selector(syn_data, date(2026, 1, 1)).quarter_value(METRICS["operating_cash_flow"], q, cal)
    assert v.status == "derived" and v.value == synthetic.OCF[2025][2]
    assert v.formula == "YTD through Q3 − YTD through Q2"
    assert len(v.sources) == 2 and {s.period_end for s in v.sources} == {date(2025, 3, 31), date(2024, 12, 31)}


def test_q4_is_derived_from_annual_minus_nine_months(syn_data):
    cal = syn_data.calendar
    q = cal.quarter_ending(date(2025, 6, 30))
    sel = _selector(syn_data, date(2026, 1, 1))
    for m, truth in (("revenue", synthetic.REVENUE), ("operating_cash_flow", synthetic.OCF), ("capex", synthetic.CAPEX)):
        v = sel.quarter_value(METRICS[m], q, cal)
        assert v.status == "derived" and v.value == truth[2025][3], m
        assert v.formula == "FY − YTD through Q3"
        assert {s.form for s in v.sources} == {"10-K", "10-Q"}


def test_q1_cash_flow_is_reported_not_derived(syn_data):
    cal = syn_data.calendar
    q = cal.quarter_ending(date(2024, 9, 30))
    v = _selector(syn_data, date(2026, 1, 1)).quarter_value(METRICS["operating_cash_flow"], q, cal)
    assert v.status == "reported" and v.value == synthetic.OCF[2025][0]


def test_instant_values_are_point_in_time(syn_data):
    cal = syn_data.calendar
    q = cal.quarter_ending(date(2024, 12, 31))
    v = _selector(syn_data, date(2026, 1, 1)).quarter_value(METRICS["cash"], q, cal)
    assert v.basis == "instant" and v.period_start is None and v.value == synthetic.CASH[(2025, 1)]


def test_missing_metric_is_missing_not_zero(syn_data):
    cal = syn_data.calendar
    q = cal.quarter_ending(date(2024, 12, 31))
    v = _selector(syn_data, date(2026, 1, 1)).quarter_value(METRICS["debt_noncurrent"], q, cal)
    assert v.status == "missing" and v.value is None and "Shown as missing, not zero" in v.notes[0]


def test_as_of_date_blocks_later_restatement(syn_data):
    cal = syn_data.calendar
    q = cal.quarter_ending(date(2024, 9, 30))  # FY2025 Q1, restated in the FY2026 Q1 10-Q
    original_filed = date(2024, 10, 25)
    early = _selector(syn_data, original_filed).quarter_value(METRICS["revenue"], q, cal)
    late = _selector(syn_data, date(2026, 1, 1)).quarter_value(METRICS["revenue"], q, cal)
    assert early.value == synthetic.REVENUE[2025][0] and not early.restated
    assert late.value == synthetic.RESTATED_FY2025_Q1_REVENUE and late.restated
    assert late.originally_reported == synthetic.REVENUE[2025][0]
    assert "later revised" in late.selection_reason


def test_facts_filed_after_as_of_are_invisible(syn_data):
    sel = _selector(syn_data, date(2023, 1, 1))
    assert sel.obs["filed"].max() <= date(2023, 1, 1)
