"""Regression tests on real Salesforce and Adobe SEC data (cached, unmodified responses in
tests/fixtures/real).

Expected values come from evaluation/verification/<TICKER>_reference.csv, read from the
statement pages of the filings, not produced by this code. See docs/REAL_DATA_VERIFICATION.md.
"""

import importlib.util
import os
import sys
from datetime import date
from pathlib import Path

import pytest

from earnings_monitor.analysis import analyze
from earnings_monitor.config import COMPANIES, Settings
from earnings_monitor.financial_normalization.metrics import METRICS
from earnings_monitor.financial_normalization.selection import FactSelector
from earnings_monitor.pipeline import load_company

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "tests" / "fixtures" / "real"
M = 1_000_000


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    s = Settings("fixture", tmp_path_factory.mktemp("real"), REAL, None, 4)
    return {t: load_company(COMPANIES[t], s)[0] for t in ("CRM", "ADBE")}


def test_fiscal_calendars(real):
    crm, adbe = real["CRM"].calendar, real["ADBE"].calendar
    q = crm.quarter_ending(date(2026, 1, 31))
    assert (q.fiscal_year, q.quarter, q.start, q.fy_start) == (2026, 4, date(2025, 11, 1), date(2025, 2, 1))
    q = adbe.quarter_ending(date(2025, 11, 28))
    assert (q.fiscal_year, q.quarter, q.start, q.fy_start) == (2025, 4, date(2025, 8, 30), date(2024, 11, 30))
    # Adobe's 52/53-week year: FY2024 Q1 ended on Mar 1, 2024 (a 13-week quarter starting Dec 2, 2023)
    q = adbe.quarter_ending(date(2024, 3, 1))
    assert (q.fiscal_year, q.quarter, q.start) == (2024, 1, date(2023, 12, 2))


def test_annual_headline_values(real):
    a = analyze(real["CRM"], "0001108524-26-000060", "annual")
    by = {c.metric_id: c for c in a.changes}
    assert by["revenue"].current.value == 41_525 * M and by["revenue"].prior.value == 37_895 * M
    assert by["operating_income"].current.value == 8_331 * M
    assert by["deferred_revenue_current"].current.value == 24_317 * M
    a = analyze(real["ADBE"], "0000796343-26-000003", "annual")
    by = {c.metric_id: c for c in a.changes}
    assert by["revenue"].current.value == 23_769 * M and by["net_income"].current.value == 7_130 * M
    assert by["capex"].current.value == 179 * M  # printed as (179) under investing activities


def test_adobe_debt_uses_the_balance_sheet_lines(real):
    """Adobe tags non-current debt with LongTermDebt and current debt with DebtCurrent; the
    default concept lists would show long-term debt as missing and current debt as 1,500M."""
    d = real["ADBE"]
    sel = FactSelector(d.obs, d.company, date(2026, 1, 15))
    cur = sel.instant_value(METRICS["debt_current"], date(2024, 11, 29), "")
    lt = sel.instant_value(METRICS["debt_noncurrent"], date(2024, 11, 29), "")
    assert (cur.value, cur.concept) == (1_499 * M, "DebtCurrent")
    assert (lt.value, lt.concept) == (4_129 * M, "LongTermDebt")
    assert "company-specific" in lt.selection_reason


def test_salesforce_long_term_debt_is_not_total_debt(real):
    """Salesforce reports LongTermDebt as the total (current + non-current); the override for
    Adobe must not apply to Salesforce."""
    d = real["CRM"]
    sel = FactSelector(d.obs, d.company, date(2026, 3, 2))
    lt = sel.instant_value(METRICS["debt_noncurrent"], date(2026, 1, 31), "")
    assert (lt.value, lt.concept) == (10_439 * M, "LongTermDebtNoncurrent")


def test_salesforce_noncurrent_unearned_revenue_is_missing_not_zero(real):
    a = analyze(real["CRM"], "0001108524-26-000060", "annual")
    v = next(c for c in a.changes if c.metric_id == "deferred_revenue_noncurrent").current
    assert v.value is None and v.status == "missing"


def test_adobe_quarterly_cash_flow_is_derived_from_ytd(real):
    """Adobe's 10-Qs print only year-to-date cash flows; Q2 = six months − three months."""
    a = analyze(real["ADBE"], "0000796343-25-000073", "yoy")
    v = next(c for c in a.changes if c.metric_id == "operating_cash_flow").current
    assert v.status == "derived" and v.value == (4_673 - 2_482) * M  # 6M 4,673 − Q1 2,482


@pytest.mark.parametrize("ticker", ["CRM", "ADBE"])
def test_full_reconciliation_passes(ticker, tmp_path, monkeypatch):
    """Runs evaluation/verification/reconcile.py offline; every check must pass."""
    monkeypatch.setenv("EM_MODE", "fixture")
    monkeypatch.setenv("EM_FIXTURE_DIR", str(REAL))
    monkeypatch.setenv("EM_DATA_DIR", str(tmp_path))
    here = ROOT / "evaluation" / "verification"
    monkeypatch.syspath_prepend(str(here))
    spec = importlib.util.spec_from_file_location("reconcile_under_test", here / "reconcile.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "HERE", tmp_path)  # write reports to tmp, read reference from a copy
    (tmp_path / f"{ticker}_reference.csv").write_bytes((here / f"{ticker}_reference.csv").read_bytes())
    monkeypatch.setattr(sys, "argv", ["reconcile.py", ticker])
    assert mod.main() == 0
    assert os.path.exists(tmp_path / f"{ticker}_reconciliation.md")
