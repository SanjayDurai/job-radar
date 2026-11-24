"""Run bookkeeping: new / seen-again / closed jobs and company health (needs TEST_DATABASE_URL)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from radar.adapters import JobPosting
from radar.models import Company, CompanyRun, Job, Run
from radar.run import CompanyResult, job_key, normalize_url, save_company_result


def _company(s) -> Company:
    c = Company(slug="acme", name="Acme", priority=1, priority_label="P1 Dream", region="chennai",
                region_label="Chennai", country="India", careers_url="https://acme.example/careers")  # fmt: skip
    s.add(c)
    s.flush()
    return c


def _posting(i: str, title="ML Engineer") -> tuple[JobPosting, str]:
    return JobPosting(
        external_id=i, title=title, url=f"https://acme.example/jobs/{i}", location="Chennai, India"
    ), "AI/ML title; Chennai"


def test_new_seen_and_closed(db_session):
    s = db_session
    c = _company(s)
    run1 = Run(trigger="local")
    s.add(run1)
    s.flush()
    t1 = datetime(2026, 11, 20, tzinfo=UTC)
    new, matched = save_company_result(s, run1, CompanyResult(c.id, "ok", 50, [_posting("1"), _posting("2")]), t1)
    s.commit()
    assert (new, matched) == (2, 2)
    assert c.health == "ok" and c.last_success_at == t1

    # Next day: job 1 still open, job 2 gone, job 3 new
    run2 = Run(trigger="local")
    s.add(run2)
    s.flush()
    t2 = t1 + timedelta(days=1)
    new, _ = save_company_result(s, run2, CompanyResult(c.id, "ok", 51, [_posting("1"), _posting("3")]), t2)
    s.commit()
    assert new == 1
    jobs = {j.external_key: j for j in s.scalars(select(Job))}
    assert jobs["1"].is_open and jobs["1"].first_seen == t1 and jobs["1"].last_seen == t2
    assert not jobs["2"].is_open and jobs["2"].closed_at == t2
    assert jobs["3"].first_seen == t2


def test_failed_company_keeps_jobs_open_and_records_error(db_session):
    s = db_session
    c = _company(s)
    run = Run(trigger="local")
    s.add(run)
    s.flush()
    now = datetime(2026, 11, 20, tzinfo=UTC)
    save_company_result(s, run, CompanyResult(c.id, "ok", 1, [_posting("1")]), now)
    save_company_result(s, run, CompanyResult(c.id, "failed", error="FetchError: HTTP 503"), now + timedelta(days=1))
    s.commit()
    assert c.health == "failing" and "503" in c.last_error
    assert s.scalar(select(Job)).is_open  # a broken fetch must not mark everything closed
    assert [r.status for r in s.scalars(select(CompanyRun).order_by(CompanyRun.id))] == ["ok", "failed"]


def test_manual_company(db_session):
    s = db_session
    c = _company(s)
    run = Run(trigger="local")
    s.add(run)
    s.flush()
    save_company_result(s, run, CompanyResult(c.id, "manual"), datetime.now(UTC))
    assert c.health == "manual"


def test_job_key_falls_back_to_normalized_url():
    p = JobPosting(external_id="", title="x", url="https://Acme.example/jobs/9/?utm=1#apply")
    assert job_key(p) == "https://acme.example/jobs/9"
    assert normalize_url("https://A.com/x/") == "https://a.com/x"
