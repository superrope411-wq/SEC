from datetime import date

from earnings_monitor.calculations.flags import evaluate
from earnings_monitor.calculations.measures import compare, derive
from earnings_monitor.models import MetricValue


def mv(metric_id, value, status="reported", unit="USD", concept="X", label=None):
    return MetricValue(company="T", cik=1, metric_id=metric_id, metric_label=label or metric_id, unit=unit,
                       period_type="duration", basis="quarter", period_start=date(2025, 1, 1),
                       period_end=date(2025, 3, 31), period_label="FY2025 Q3", value=value, status=status,
                       concept=concept)


def test_free_cash_flow_definition_and_provenance():
    v = derive("free_cash_flow", {"Operating cash flow": mv("ocf", 100.0), "Capital expenditures": mv("capex", 30.0)},
               lambda a, b: a - b)
    assert v.value == 70.0 and v.status == "derived"
    assert v.formula == "Operating cash flow − Capital expenditures"
    assert v.input_values == {"Operating cash flow": 100.0, "Capital expenditures": 30.0}


def test_margin_with_zero_or_negative_revenue_is_not_meaningful():
    for rev in (0.0, -5.0):
        v = derive("operating_margin", {"Operating income": mv("oi", 10.0), "Revenue": mv("rev", rev)},
                   lambda a, b: a / b, denominator="Revenue")
        assert v.status == "not_meaningful" and v.value is None


def test_missing_input_propagates():
    v = derive("net_margin", {"Net income": mv("ni", None, "missing"), "Revenue": mv("rev", 10.0)}, lambda a, b: a / b,
               denominator="Revenue")
    assert v.status == "missing" and "Net income" in v.notes[0]


def test_percent_change_and_negative_prior():
    c = compare(mv("rev", 120.0), mv("rev", 100.0), "yoy")
    assert c.abs_change == 20.0 and abs(c.pct_change - 0.2) < 1e-12
    c = compare(mv("oi", 5.0), mv("oi", -10.0), "yoy")
    assert c.abs_change == 15.0 and c.pct_change is None and "not meaningful" in c.note


def test_ratio_change_in_percentage_points():
    c = compare(mv("m", 0.42, "derived", unit="ratio"), mv("m", 0.40, "derived", unit="ratio"), "yoy")
    assert c.change_kind == "percentage_points" and abs(c.abs_change - 2.0) < 1e-9


def test_concept_switch_is_noted():
    c = compare(mv("rev", 1.0, concept="Revenues"), mv("rev", 1.0, concept="SalesRevenueNet"), "yoy")
    assert "Concept changed" in c.note


def test_flags_explain_threshold():
    changes = {"revenue": compare(mv("revenue", 115.0, label="Revenue"), mv("revenue", 100.0, label="Revenue"), "yoy")}
    f = evaluate(changes, "Same quarter, prior fiscal year")
    assert len(f) == 1 and f[0].rule_id == "revenue_change" and "at least 10%" in f[0].why
    assert not evaluate({"revenue": compare(mv("revenue", 105.0), mv("revenue", 100.0), "yoy")}, "x")
