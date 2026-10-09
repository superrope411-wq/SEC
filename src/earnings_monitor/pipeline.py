"""End-to-end load for one company: raw cache → parse → SQLite → calendar."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd

from earnings_monitor import PIPELINE_VERSION
from earnings_monitor.analysis import CompanyData
from earnings_monitor.config import Company, Settings
from earnings_monitor.financial_normalization.calendar import build_calendar
from earnings_monitor.financial_normalization.observations import (
    filings_from_facts, filings_from_submissions, flatten_companyfacts,
)
from earnings_monitor.ingestion.ingest import ingest_company
from earnings_monitor.storage.db import Store


class DataMismatch(RuntimeError):
    pass


def load_company(company: Company, settings: Settings, refresh: bool = False, client=None) -> tuple[CompanyData, dict]:
    t0 = time.perf_counter()
    res = ingest_company(company, settings, refresh=refresh, client=client)
    facts_doc = res.documents["companyfacts"]
    subs_doc = res.documents["submissions"]

    store = Store(settings.db_path)
    try:
        reprocessed = not store.has_loaded(facts_doc.sha256, "companyfacts", PIPELINE_VERSION)
        if reprocessed:
            raw = facts_doc.read_json()
            if int(raw["cik"]) != company.cik:
                raise DataMismatch(f"companyfacts CIK {raw['cik']} does not match {company.ticker} ({company.cik})")
            obs = flatten_companyfacts(raw)
            store.save_observations(obs, facts_doc.sha256)
            store.record_raw(facts_doc.sha256, "companyfacts", company.cik, facts_doc.path, facts_doc.url,
                             facts_doc.fetched_at, facts_doc.source, PIPELINE_VERSION)
        obs = store.load_observations(facts_doc.sha256)

        subs = subs_doc.read_json()
        if int(subs.get("cik", company.cik)) != company.cik:
            raise DataMismatch(f"submissions CIK {subs.get('cik')} does not match {company.ticker}")
        fye = subs.get("fiscalYearEnd")
        filings = _merge_filings(filings_from_submissions(subs), filings_from_facts(obs))
        store.save_filings(company.cik, filings)
        store.save_company(company.cik, company.ticker, subs.get("name", company.name), fye)
        calendar = build_calendar(obs)
        seconds = time.perf_counter() - t0
        store.record_run(started_at=datetime.now(timezone.utc).isoformat(), cik=company.cik,
                         pipeline_version=PIPELINE_VERSION, mode=settings.mode,
                         downloaded=",".join(res.downloaded), reused=",".join(res.reused),
                         observations=len(obs), reprocessed=int(reprocessed), seconds=round(seconds, 3))
    finally:
        store.close()

    data = CompanyData(company, obs, filings, calendar, facts_doc.source, facts_doc.sha256, facts_doc.fetched_at, fye)
    stats = {"seconds": seconds, "downloaded": res.downloaded, "reused": res.reused,
             "observations": len(obs), "reprocessed": reprocessed, "filings": len(filings)}
    return data, stats


def _merge_filings(from_subs: pd.DataFrame, from_facts: pd.DataFrame) -> pd.DataFrame:
    """Submissions is authoritative (it has report dates and document names). Its 'recent'
    list can omit older filings, so add any periodic filing that appears only in the facts."""
    if from_subs.empty:
        return from_facts
    extra = from_facts[~from_facts["accn"].isin(from_subs["accn"])]
    return pd.concat([from_subs, extra], ignore_index=True).sort_values("filed", ascending=False).reset_index(drop=True)
