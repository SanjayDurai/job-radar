"""One fetch run over all active companies.

- Network work happens in worker threads (shared PoliteClient keeps per-host politeness).
- All DB writes happen on the main thread, one company at a time, so one bad company never
  breaks the run: its error is recorded on `company_runs` / `companies.last_error` and we move on.
- Only postings that pass the title + location pre-filter are stored and get a description fetch,
  and a description is fetched once per job (not every day).
"""

from __future__ import annotations

import hashlib
import logging
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from radar.adapters import FetchContext, JobPosting, get_adapter
from radar.adapters.base import clean_text
from radar.companies_config import load_companies_yaml
from radar.db import session_scope
from radar.filters import check_location, check_title, mentions_any_place
from radar.http import PoliteClient
from radar.models import Company, CompanyRun, Job, JobScore, Run
from radar.scoring.llm import LLMScorer
from radar.scoring.pipeline import score_open_jobs
from radar.settings import profile, scoring

log = logging.getLogger(__name__)


@dataclass
class CompanyResult:
    company_id: int
    status: str  # ok | failed | manual
    total_listed: int = 0
    matched: list[tuple[JobPosting, str]] = field(default_factory=list)  # (posting, filter reason)
    error: str | None = None
    duration_ms: int = 0


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def job_key(p: JobPosting) -> str:
    return (p.external_id or normalize_url(p.url))[:300]


def sync_sources_from_yaml(session: Session) -> None:
    """companies.yaml is the source of truth for fetch config; copy it into the DB before a run."""
    entries = load_companies_yaml()
    for c in session.scalars(select(Company)):
        e = entries.get(c.slug)
        if not e:
            continue
        st, cfg = e.get("source_type", "unknown"), e.get("source_config") or {}
        if c.source_type != st or (c.source_config or {}) != cfg:
            c.source_type, c.source_config = st, cfg


def fetch_company(company: dict[str, Any], client: PoliteClient, known_with_description: set[str]) -> CompanyResult:
    """Runs in a worker thread. Never raises."""
    t0 = time.monotonic()
    res = CompanyResult(company_id=company["id"], status="ok")
    adapter = get_adapter(company["source_type"])
    if company["source_type"] == "manual" or adapter is None:
        res.status = "manual"
        res.error = None if company["source_type"] == "manual" else f"no adapter for source_type '{company['source_type']}'"
        return res
    cfg = company["source_config"] or {}
    ctx = FetchContext(client=client)
    try:
        postings = adapter.list_jobs(cfg, ctx)
        res.total_listed = len(postings)
        for p in postings:
            if not p.title or not p.url:
                continue
            tv = check_title(p.title)
            if not tv.ok:
                continue
            lv = check_location(p.all_locations_text(), company["region"], company["country"], p.is_remote)
            if not lv.ok:
                continue
            res.matched.append((p, f"{tv.reason}; {lv.reason}"))
        kept: list[tuple[JobPosting, str]] = []
        for p, reason in res.matched:
            if not p.description and job_key(p) not in known_with_description and adapter.needs_description_fetch:
                had_location = bool(p.all_locations_text())
                try:
                    p.description = adapter.fetch_description(p, cfg, ctx)
                except Exception as e:  # one bad detail page shouldn't fail the company
                    log.warning("%s: description fetch failed for %s: %s", company["slug"], p.url, e)
                    if not had_location:
                        # No location and no description: we can't tell if it fits. Skip it this run;
                        # it is retried tomorrow (e.g. after a rate limit) instead of stored half-empty.
                        continue
                # HTML sources often reveal the location only on the detail page: check it now.
                # If even the page has no structured location, use the top of the description,
                # where career pages normally state it.
                if not had_location:
                    head = (p.description or "")[:800]
                    where = p.all_locations_text() or (head if mentions_any_place(head) else "")
                    if where:  # otherwise the location stays unknown (scored cautiously later)
                        lv = check_location(where, company["region"], company["country"], p.is_remote)
                        if not lv.ok:
                            continue
                        reason = f"{reason.split(';')[0]}; {lv.reason}"
            kept.append((p, reason))
        res.matched = kept
    except Exception as e:
        res.status = "failed"
        res.error = f"{type(e).__name__}: {e}"[:1000]
        log.debug("%s failed:\n%s", company["slug"], traceback.format_exc())
    res.duration_ms = int((time.monotonic() - t0) * 1000)
    return res


def save_company_result(session: Session, run: Run, res: CompanyResult, now: datetime) -> tuple[int, int]:
    """Upsert jobs, close vanished ones, update health. Returns (new_jobs, matched_jobs)."""
    company = session.get(Company, res.company_id)
    assert company is not None
    session.add(CompanyRun(run_id=run.id, company_id=company.id, status=res.status, jobs_found=res.total_listed,
                           jobs_matched=len(res.matched), error=res.error, duration_ms=res.duration_ms))  # fmt: skip
    company.last_attempt_at = now
    if res.status == "manual":
        company.health, company.last_error = "manual", res.error
        return 0, 0
    if res.status == "failed":
        company.health, company.last_error = "failing", res.error
        return 0, 0

    company.health, company.last_error, company.last_success_at = "ok", None, now
    existing = {j.external_key: j for j in session.scalars(select(Job).where(Job.company_id == company.id))}
    seen_keys: set[str] = set()
    new_count = 0
    for p, reason in res.matched:
        key = job_key(p)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        # Pages sometimes carry broken characters; store clean UTF-8 only
        p.title, p.description, p.location = clean_text(p.title) or "", clean_text(p.description), clean_text(p.location)
        p.locations = [clean_text(x) or "" for x in p.locations]
        desc_hash = hashlib.sha256(p.description.encode()).hexdigest() if p.description else None
        job = existing.get(key)
        if job is None:
            job = Job(company_id=company.id, external_key=key, first_seen=now)
            session.add(job)
            new_count += 1
        job.title = p.title
        job.url = p.url
        job.location = p.location
        job.locations = p.locations
        job.is_remote = p.is_remote
        job.department = p.department
        job.employment_type = p.employment_type
        job.posted_at = p.posted_at or job.posted_at
        if p.description:  # keep the stored description when we skipped re-fetching it
            job.description, job.description_hash = p.description, desc_hash
        job.salary_min, job.salary_max = p.salary_min, p.salary_max
        job.salary_currency, job.salary_period = p.salary_currency, p.salary_period
        job.passes_filter, job.filter_reason = True, reason
        job.last_seen, job.is_open, job.closed_at = now, True, None

    # Anything previously open for this company that we didn't see today has closed.
    vanished = [j.id for k, j in existing.items() if j.is_open and k not in seen_keys]
    if vanished:
        session.execute(update(Job).where(Job.id.in_(vanished)).values(is_open=False, closed_at=now))
    return new_count, len(seen_keys)


def run_all(trigger: str = "local", only: list[str] | None = None, workers: int = 6, use_llm: bool = True) -> Run:
    t0 = time.monotonic()
    now = datetime.now(UTC)
    with session_scope() as s:
        sync_sources_from_yaml(s)
        # A run killed mid-way (timeout, cancelled CI job) would otherwise stay "running" forever.
        s.execute(
            update(Run)
            .where(Run.status == "running", Run.started_at < now - timedelta(hours=3))
            .values(status="failed", error="run did not finish (killed or timed out)")
        )
        run = Run(trigger=trigger, status="running", started_at=now)
        s.add(run)
        s.flush()
        q = select(Company).where(Company.active.is_(True)).order_by(Company.sheet_no)
        if only:
            q = q.where(Company.slug.in_(only))
        companies = [
            {"id": c.id, "slug": c.slug, "name": c.name, "region": c.region, "country": c.country,
             "source_type": c.source_type, "source_config": c.source_config}
            for c in s.scalars(q)
        ]  # fmt: skip
        known: dict[int, set[str]] = {}
        for cid, key in s.execute(select(Job.company_id, Job.external_key).where(Job.description.is_not(None))):
            known.setdefault(cid, set()).add(key)
        run_id = run.id

    totals = {"ok": 0, "failed": 0, "manual": 0, "found": 0, "new": 0}
    with PoliteClient() as client, ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_company, c, client, known.get(c["id"], set())): c for c in companies}
        for fut in as_completed(futures):
            c = futures[fut]
            res = fut.result()
            with session_scope() as s:
                run = s.get(Run, run_id)
                new, _matched = save_company_result(s, run, res, now)
            totals[res.status] += 1
            totals["found"] += res.total_listed
            totals["new"] += new
            log.info("%-28s %-8s listed=%-5d matched=%-4d new=%-3d %s", c["slug"], res.status, res.total_listed,
                     len(res.matched), new, res.error or "")  # fmt: skip

    # Score after fetching (a scoring problem must not lose the fetched jobs)
    details: dict[str, Any] = {}
    matches_new = llm_calls = 0
    try:
        with session_scope() as s:
            llm = LLMScorer(scoring(), profile()) if use_llm else None
            stats = score_open_jobs(s, llm)
            details["scoring"] = {"scored": stats.scored, "excluded": stats.excluded, "llm_cached": stats.llm_cached,
                                  "llm_errors": stats.llm_errors, "llm_note": stats.llm_note}  # fmt: skip
            llm_calls = stats.llm_calls
            matches_new = s.scalar(
                select(func.count())
                .select_from(JobScore)
                .join(Job, Job.id == JobScore.job_id)
                .where(Job.first_seen == now, Job.is_open, JobScore.excluded.is_(False),
                       JobScore.final_score >= int(scoring().get("new_match_min_score", 50)))
            ) or 0  # fmt: skip
    except Exception as e:
        log.error("scoring failed: %s", e)
        details["scoring_error"] = f"{type(e).__name__}: {e}"[:500]

    with session_scope() as s:
        run = s.get(Run, run_id)
        run.finished_at = datetime.now(UTC)
        run.duration_s = int(time.monotonic() - t0)
        run.companies_total = len(companies)
        run.companies_ok, run.companies_failed, run.companies_manual = totals["ok"], totals["failed"], totals["manual"]
        run.jobs_found, run.jobs_new = totals["found"], totals["new"]
        run.matches_new, run.llm_calls, run.details = matches_new, llm_calls, details
        run.status = (
            "ok" if totals["failed"] == 0 and "scoring_error" not in details else ("partial" if totals["ok"] else "failed")
        )
        return run
