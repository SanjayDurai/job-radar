"""Score every open job: rules for all (cheap, so config changes apply immediately), then the
optional LLM for the best rule-scored jobs that don't have a cached LLM result yet."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.models import Company, Job, JobScore
from radar.scoring.llm import LLMScorer, LLMUnavailable, content_hash
from radar.scoring.rules import CompanyInput, JobInput, RuleResult, final_score, score_rules
from radar.settings import profile, scoring

log = logging.getLogger(__name__)


@dataclass
class ScoreStats:
    scored: int = 0
    excluded: int = 0
    llm_calls: int = 0
    llm_cached: int = 0
    llm_errors: int = 0
    llm_note: str | None = None


def _location_text(job: Job) -> str:
    return " | ".join(x for x in [job.location, *(job.locations or [])] if x)


def _rule_result(job: Job, company: Company) -> RuleResult:
    return score_rules(
        JobInput(
            title=job.title,
            description=job.description,
            location_text=_location_text(job),
            is_remote=job.is_remote,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            salary_currency=job.salary_currency,
            salary_period=job.salary_period,
        ),
        CompanyInput(region=company.region, country=company.country, priority=company.priority),
        scoring(),
        profile(),
    )


def _apply(score_row: JobScore, rule: RuleResult, priority: int, now: datetime) -> None:
    llm_score = score_row.llm_score if score_row.llm_result else None
    final, extra = final_score(rule, llm_score, priority, scoring())
    score_row.rule_score = rule.score
    score_row.rule_reasons = rule.reasons + extra
    score_row.region_tag = rule.region_tag
    score_row.below_pay_bar = rule.below_pay_bar
    score_row.years_required = Decimal(str(rule.years_required)) if rule.years_required is not None else None
    score_row.visa_signal = rule.visa_signal
    score_row.salary_lpa = Decimal(str(rule.salary_lpa)) if rule.salary_lpa is not None else None
    score_row.excluded, score_row.exclude_reason = rule.excluded, rule.exclude_reason
    # The LLM reads the whole posting, so its experience estimate catches "5+ years" asks that the
    # regex parser misses (it takes the smallest number it finds).
    est = (score_row.llm_result or {}).get("est_years_required")
    limit = scoring().get("exclude_if_years_at_least", 5)
    if not rule.excluded and isinstance(est, int | float) and est >= limit:
        score_row.excluded, score_row.exclude_reason = True, f"LLM: needs about {est:g}+ years of experience"
    score_row.final_score = final
    score_row.scored_at = now


def score_open_jobs(session: Session, llm: LLMScorer | None = None, company_ids: list[int] | None = None) -> ScoreStats:
    stats = ScoreStats()
    now = datetime.now(UTC)
    q = select(Job, Company).join(Company).where(Job.is_open.is_(True), Job.passes_filter.is_(True))
    if company_ids:
        q = q.where(Job.company_id.in_(company_ids))
    rows = list(session.execute(q).all())
    existing = {s.job_id: s for s in session.scalars(select(JobScore).where(JobScore.job_id.in_([j.id for j, _ in rows])))}

    # 1) rules for everything
    rule_results: dict[int, RuleResult] = {}
    for job, company in rows:
        rule = _rule_result(job, company)
        rule_results[job.id] = rule
        row = existing.get(job.id)
        if row is None:
            row = JobScore(job_id=job.id, rule_score=0, final_score=0)
            session.add(row)
            existing[job.id] = row
        _apply(row, rule, company.priority, now)
        stats.scored += 1
        stats.excluded += int(rule.excluded)
    session.commit()

    # 2) LLM for the best candidates without a cached result (highest rule score first)
    if llm is None or not llm.available:
        if llm is not None and not llm.enabled_by_config:
            stats.llm_note = "LLM off (no GROQ_API_KEY)"
        return stats
    candidates = []
    for job, company in rows:
        rule = rule_results[job.id]
        if rule.excluded or rule.score < llm.min_rule_score or not job.description:
            continue
        h = content_hash(llm.model, job.title, job.description[: llm.max_chars])
        if existing[job.id].llm_content_hash == h and existing[job.id].llm_result:
            stats.llm_cached += 1
            continue
        candidates.append((rule.score, job, company, h))
    candidates.sort(key=lambda c: (-c[0], c[2].priority))  # best rule score first, then P1 before P2
    for _, job, company, h in candidates:
        if not llm.available:
            break
        try:
            result = llm.score(company=company.name, country=company.country, title=job.title,
                               location=_location_text(job), description=job.description or "")  # fmt: skip
        except LLMUnavailable as e:
            stats.llm_note = str(e)
            break
        except Exception as e:  # bad JSON / transient API error: skip this job, keep going
            stats.llm_errors += 1
            log.warning("LLM scoring failed for job %s: %s", job.id, e)
            continue
        row = existing[job.id]
        row.llm_score, row.llm_result, row.llm_model = result.score, result.data, result.model
        row.llm_content_hash, row.llm_scored_at = h, now
        _apply(row, rule_results[job.id], company.priority, now)
        session.commit()
        stats.llm_calls += 1
    if stats.llm_note is None and llm.calls >= llm.max_calls and len(candidates) > stats.llm_calls:
        stats.llm_note = f"LLM call cap ({llm.max_calls}) reached; {len(candidates) - stats.llm_calls} jobs wait for the next run"
    return stats
