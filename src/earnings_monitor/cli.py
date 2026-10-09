"""Command line: ingest a company, analyze a filing, export, and show timing."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from earnings_monitor.analysis import COMPARISONS, AnalysisError, analyze, available_comparisons
from earnings_monitor.config import COMPANIES, ConfigError, load_settings
from earnings_monitor.exports.tables import to_csv, to_excel
from earnings_monitor.ingestion.sec_client import SecError
from earnings_monitor.pipeline import load_company


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="earnings-monitor")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("ingest", help="download (or refresh) a company's SEC data and load it")
    i.add_argument("ticker", choices=sorted(COMPANIES))
    i.add_argument("--refresh", action="store_true", help="re-download even if cached recently (new-filing check)")
    f = sub.add_parser("filings", help="list analyzable filings")
    f.add_argument("ticker", choices=sorted(COMPANIES))
    a = sub.add_parser("analyze", help="analyze one filing and optionally export")
    a.add_argument("ticker", choices=sorted(COMPANIES))
    a.add_argument("--accn", help="accession number (default: latest filing)")
    a.add_argument("--comparison", choices=sorted(COMPARISONS), default="yoy")
    a.add_argument("--xlsx", type=Path)
    a.add_argument("--csv", type=Path)
    args = p.parse_args(argv)

    try:
        settings = load_settings()
        company = COMPANIES[args.ticker]
        data, stats = load_company(company, settings, refresh=getattr(args, "refresh", False))
    except (ConfigError, SecError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    src = "FIXTURE (local files)" if data.data_source == "fixture" else "SEC EDGAR"
    print(f"{company.name}: {stats['observations']:,} observations from {src}; "
          f"{stats['filings']} periodic filings; downloaded={stats['downloaded'] or 'none'}; "
          f"reprocessed={stats['reprocessed']}; {stats['seconds']:.2f}s")
    if args.cmd == "ingest":
        return 0
    if args.cmd == "filings":
        for r in data.filings.itertuples():
            q = data.calendar.quarter_ending(r.report_date) if r.report_date else None
            print(f"{r.accn}  {r.form:<7} filed {r.filed}  period {r.report_date}  {q.long_label if q else '?'}")
        return 0
    accn = args.accn or data.filings.iloc[0].accn
    try:
        if args.comparison not in available_comparisons(data, accn):
            print(f"error: comparison {args.comparison} is not valid for {accn}", file=sys.stderr)
            return 2
        result = analyze(data, accn, args.comparison)
    except AnalysisError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"\n{result.filing.form} {result.filing.accn} filed {result.filing.filed}: {result.current_label} vs {result.prior_label}")
    print(f"Comparison basis: {result.comparison_label}\n")
    for c in result.changes:
        cur = _fmt(c.current.value, c.unit)
        pri = _fmt(c.prior.value, c.unit)
        if c.abs_change is None:
            ch = "n/a"
        elif c.change_kind == "percentage_points":
            ch = f"{c.abs_change:+.1f} pp"
        else:
            ch = f"{c.abs_change:+,.0f}" + (f" ({c.pct_change:+.1%})" if c.pct_change is not None else "")
        print(f"{c.metric_label:<34} {cur:>18} {pri:>18} {ch:>22}  [{c.current.status}]")
    if result.findings:
        print("\nFindings:")
        for fd in result.findings:
            print(f"  [{fd.priority}] {fd.title}\n      {fd.why}")
    warn = [i for i in result.issues if i.severity != "info"]
    if warn:
        print("\nWarnings:")
        for i in warn:
            print(f"  {i.severity}: {i.message}")
    if args.xlsx:
        args.xlsx.write_bytes(to_excel(result))
        print(f"\nwrote {args.xlsx}")
    if args.csv:
        args.csv.write_bytes(to_csv(result))
        print(f"wrote {args.csv}")
    return 0


def _fmt(v, unit):
    if v is None:
        return "—"
    if unit == "ratio":
        return f"{v:.1%}"
    return f"{v:,.0f}"


if __name__ == "__main__":
    sys.exit(main())
