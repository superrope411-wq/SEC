"""Choose a valid pair of filings and section, run the comparison, and rank what changed.

Rules for a valid comparison (PROJECT_SPEC.md section 4C):
- Same form only: a 10-K against the previous 10-K; a 10-Q against the 10-Q for the same
  fiscal quarter a year earlier (or, if asked, the previous 10-Q). A 10-Q never stands in for a
  10-K: a 10-Q only has to report material changes to risk factors, and many refer back to the
  annual report, so a short 10-Q section is not evidence that a risk was removed.
- A section that is missing, or that only incorporates another document by reference, is
  reported as such and not diffed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from earnings_monitor.analysis import CompanyData, filing_info, filing_quarter
from earnings_monitor.config import Settings
from earnings_monitor.disclosure_diff.compare import Change, SectionDiff, compare_units, units
from earnings_monitor.disclosure_diff.significance import Significance, assess
from earnings_monitor.evidence.retrieve import build_index

SECTIONS = {
    "risk_factors": ("Risk Factors", {"10-K": "PI-I1A", "10-Q": "PII-I1A"}),
    "mdna": ("Management's Discussion and Analysis", {"10-K": "PII-I7", "10-Q": "PI-I2"}),
}
BASES = {"prior_year": "Same period, prior year", "sequential": "Previous 10-Q (sequential)"}
_BY_REFERENCE = re.compile(
    r"no material changes?|incorporated (?:herein )?by reference|refer to (?:the )?(?:risk factors|part i, item 1a)"
    r"|discussed in (?:our|the) (?:annual report|form 10-k)", re.I)


class DisclosureError(ValueError):
    pass


@dataclass
class FilingRef:
    accn: str
    form: str
    filed: date
    period_label: str
    url: str


@dataclass
class RankedChange:
    change: Change
    significance: Significance


@dataclass
class DisclosureComparison:
    company: str
    section_id: str
    section_title: str
    basis: str
    new: FilingRef
    old: FilingRef
    status: str  # "compared", "incorporated_by_reference", "section_missing"
    message: str = ""
    diff: SectionDiff | None = None
    ranked: list[RankedChange] = field(default_factory=list)
    noise: dict[str, int] = field(default_factory=dict)


def _ref(data: CompanyData, accn: str) -> FilingRef:
    f = filing_info(data, accn)
    return FilingRef(accn, f.form, f.filed, filing_quarter(data, f).long_label, f.url)


def comparable_filing(data: CompanyData, accn: str, basis: str = "prior_year") -> str:
    """The earlier filing of the same form that this filing's section should be compared with."""
    f = filing_info(data, accn)
    form = "10-K" if f.form.startswith("10-K") else "10-Q"
    q = filing_quarter(data, f)
    cands = data.filings[(data.filings["form"] == form) & (data.filings["filed"] < f.filed)]
    if basis == "sequential":
        if form == "10-K":
            raise DisclosureError("A 10-K is compared with the previous 10-K; there is no sequential 10-K.")
        target = data.calendar.previous_quarter(q)
        while target is not None and target.quarter == 4:  # Q4 is reported in the 10-K, not a 10-Q
            target = data.calendar.previous_quarter(target)
    else:
        target = data.calendar.same_quarter_prior_year(q)
    if target is None:
        raise DisclosureError(f"No earlier period to compare {q.long_label} with.")
    for r in cands.itertuples():
        if r.report_date is not None and abs((r.report_date - target.end).days) <= 7:
            return r.accn
    raise DisclosureError(f"No {form} for {target.long_label} is in the filing list.")


def compare_filings(data: CompanyData, accn: str, section_id: str, settings: Settings,
                    basis: str = "prior_year", old_accn: str | None = None, client=None) -> DisclosureComparison:
    title, by_form = SECTIONS[section_id]
    new = _ref(data, accn)
    old = _ref(data, old_accn or comparable_filing(data, accn, basis))
    form = "10-K" if new.form.startswith("10-K") else "10-Q"
    if not old.form.startswith(form):
        raise DisclosureError(f"Cannot compare a {new.form} with a {old.form}: the forms have different disclosure requirements.")
    sec = by_form[form]
    out = DisclosureComparison(data.company.ticker, section_id, title, BASES.get(basis, basis), new, old, "compared")
    new_units = units(build_index(data, new.accn, settings, client).passages, sec)
    old_units = units(build_index(data, old.accn, settings, client).passages, sec)
    for u_list, ref in ((new_units, new), (old_units, old)):
        if not u_list:
            out.status = "section_missing"
            out.message = f"{title} was not found in the {ref.form} filed {ref.filed}; nothing is compared."
            return out
        if form == "10-Q" and len(u_list) <= 4 and any(_BY_REFERENCE.search(u.text) for u in u_list):
            out.status = "incorporated_by_reference"
            out.message = (f"The {ref.form} filed {ref.filed} does not restate its {title.lower()}; it refers to an "
                           f"earlier filing: \"{u_list[0].text[:300]}\". Absence of text here is not a removal.")
            return out
    diff = compare_units(old_units, new_units, sec)
    out.diff = diff
    out.ranked = sorted((RankedChange(c, assess(c)) for c in diff.substantive), key=lambda r: -r.significance.score)
    counts = diff.counts()
    out.noise = {"unchanged": counts["unchanged"], "routine_update": counts["routine_update"],
                 "minor_edit": counts["minor_edit"], "split_or_merge": counts["split_or_merge"],
                 "reordered": diff.reordered, "heading_renames": len(diff.heading_renames)}
    return out
