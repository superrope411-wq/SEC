"""Disclosure comparison: noise suppression and change detection on small, readable cases,
plus the real Salesforce 10-K pair (saved filings in tests/fixtures/real)."""

from pathlib import Path

import pytest

from earnings_monitor.config import COMPANIES, Settings
from earnings_monitor.disclosure_diff.compare import Unit, compare_units, join_fragments, mask, normalize
from earnings_monitor.disclosure_diff.service import DisclosureError, comparable_filing, compare_filings
from earnings_monitor.disclosure_diff.significance import assess
from earnings_monitor.pipeline import load_company

REAL = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "real"

P1 = "We face intense competition across all markets for our products and services, which may adversely affect our results."
P2 = "Our revenue for fiscal year 2025 was $281.7 billion, an increase of 15% compared with fiscal year 2024."
P3 = "Cyberattacks and security vulnerabilities could lead to reduced revenue, increased costs, liability claims, or harm to our reputation."
P4 = "Government regulation of the internet and data privacy could harm our business, including laws on cross-border data transfers."


def U(*texts, heading=""):
    out = []
    for k, t in enumerate(texts):
        n = normalize(t)
        out.append(Unit(text=t, norm=n, masked=mask(n), heading=heading, position=k))
    return out


def test_identical_reordered_and_reformatted_is_not_a_change():
    old = U(P1, P2, P3)
    new = U("•  " + P3.replace("'", "’"), P1.replace(", ", ",  "), P2)
    d = compare_units(old, new)
    assert d.substantive == [] and d.counts()["unchanged"] == 3 and d.reordered >= 1


def test_routine_date_and_number_update_is_noise_but_numbers_are_listed():
    new_p2 = "Our revenue for fiscal year 2026 was $318.2 billion, an increase of 13% compared with fiscal year 2025."
    d = compare_units(U(P1, P2), U(P1, new_p2))
    c = next(c for c in d.changes if c.kind == "routine_update")
    assert d.substantive == [] and ("$281.7", "$318.2") in c.numbers_changed


def test_page_break_fragment_is_joined():
    a, b = P3.split(" increased ")
    assert len(join_fragments(U(a, "increased " + b))) == 1


def test_added_removed_and_reworded_paragraphs_are_found():
    reworded = P3.replace("could lead to", "have led and could continue to lead to") + \
        " In fiscal 2025 a nation-state actor accessed a limited number of corporate email accounts."
    d = compare_units(U(P1, P3, P4), U(P1, reworded, P2.replace("2025", "2031")))
    kinds = sorted(c.kind for c in d.substantive)
    assert kinds == ["added", "changed", "removed"]
    changed = next(c for c in d.substantive if c.kind == "changed")
    sig = assess(changed)
    assert sig.words_added > 10 and any(t.id == "cyber" for t in sig.tags)
    removed = next(c for c in d.substantive if c.kind == "removed")
    assert any(t.id == "legal_regulatory" for t in assess(removed).tags)


def test_one_word_edit_is_minor():
    d = compare_units(U(P1), U(P1.replace("may adversely", "could adversely")))
    assert [c.kind for c in d.changes] == ["minor_edit"] and d.substantive == []


def test_bullets_regrouped_into_one_paragraph_are_not_added_text():
    bullets = U("Acquisitions involve risks, including the following items listed here:",
                "difficulties integrating the operations and personnel of acquired companies;",
                "the diversion of management attention from the existing business of the company;",
                "the assumption of unknown liabilities and the risk of litigation from the transaction.")
    merged = U(" ".join(u.text for u in bullets))
    d = compare_units(bullets, merged)
    assert d.substantive == [], [c.kind for c in d.substantive]


@pytest.fixture(scope="module")
def crm(tmp_path_factory):
    s = Settings("fixture", tmp_path_factory.mktemp("crm"), REAL, None, 4)
    return load_company(COMPANIES["CRM"], s)[0], s


def test_pairs_are_same_form(crm):
    data, _ = crm
    assert comparable_filing(data, "0001108524-26-000060") == "0001108524-25-000006"  # 10-K -> prior 10-K
    assert comparable_filing(data, "0001108524-25-000088") == "0001108524-24-000022"  # Q2 -> Q2 a year earlier
    assert comparable_filing(data, "0001108524-25-000088", "sequential") == "0001108524-25-000030"
    with pytest.raises(DisclosureError):
        comparable_filing(data, "0001108524-26-000060", "sequential")


def test_real_salesforce_10k_md_and_a(crm):
    data, s = crm
    comp = compare_filings(data, "0001108524-26-000060", "mdna", s)
    assert comp.status == "compared" and comp.ranked
    texts = " ".join((r.change.new.text if r.change.new else "") for r in comp.ranked)
    # Real additions in the FY2026 10-K: the Informatica bridge credit agreement and the 2025 US tax law.
    assert "364-day" in texts and "One Big Beautiful Bill Act" in texts
    assert comp.noise["unchanged"] > 20
    # Every change links back to evidence passages of the right filing.
    for r in comp.ranked:
        if r.change.new:
            assert all(e.startswith("0001108524-26-000060:") for e in r.change.new.evidence_ids)
