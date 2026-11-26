"""Database schema (SQLAlchemy 2.0). Alembic migrations are generated from these models.

Tables
------
companies     one row per company from the Excel sheet (never deleted; `active=False` when removed)
jobs          one row per posting, keyed by (company_id, external_key)
job_scores    rule + optional LLM score for a job (LLM result cached by content hash)
job_state     my status / notes / seen flag for a job
runs          one row per fetch run (summary for the dashboard)
company_runs  per-company result inside a run (drives the health column)
app_state     small key/value store (e.g. last dashboard visit)
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _now_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    sheet_no: Mapped[int | None] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1=P1 Dream, 2=P2 Strong, 3=P3 Good
    priority_label: Mapped[str] = mapped_column(String(40), nullable=False)
    region: Mapped[str] = mapped_column(String(30), nullable=False)  # chennai|india_other|india_remote|abroad|remote_global
    region_label: Mapped[str] = mapped_column(String(80), nullable=False)
    country: Mapped[str] = mapped_column(String(80), nullable=False)
    cities: Mapped[str | None] = mapped_column(Text)
    company_type: Mapped[str | None] = mapped_column(String(120))
    why_fit: Mapped[str | None] = mapped_column(Text)
    min_ask_lpa: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    pay_vs_min: Mapped[str | None] = mapped_column(String(80))
    visa_route: Mapped[str | None] = mapped_column(Text)
    careers_url: Mapped[str] = mapped_column(Text, nullable=False)
    sheet_status: Mapped[str | None] = mapped_column(String(60))
    sheet_notes: Mapped[str | None] = mapped_column(Text)

    # Fetch configuration, synced from config/companies.yaml (the source of truth)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, server_default="unknown")
    source_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))

    # Health, updated by each run
    health: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")  # ok|failing|manual|pending
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = _now_col()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    jobs: Mapped[list[Job]] = relationship(back_populates="company")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("company_id", "external_key", name="uq_jobs_company_key"),
        Index("ix_jobs_open_first_seen", "is_open", "first_seen"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    external_key: Mapped[str] = mapped_column(String(300), nullable=False)  # ATS job id or normalized URL
    title: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(Text)
    locations: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    is_remote: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    url: Mapped[str] = mapped_column(Text, nullable=False)
    department: Mapped[str | None] = mapped_column(Text)
    employment_type: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    description_hash: Mapped[str | None] = mapped_column(String(64))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    salary_currency: Mapped[str | None] = mapped_column(String(8))
    salary_period: Mapped[str | None] = mapped_column(String(16))  # year|month|hour

    passes_filter: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    filter_reason: Mapped[str | None] = mapped_column(Text)

    first_seen: Mapped[datetime] = _now_col()
    last_seen: Mapped[datetime] = _now_col()
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    company: Mapped[Company] = relationship(back_populates="jobs")


class JobScore(Base):
    __tablename__ = "job_scores"

    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    rule_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    rule_reasons: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    region_tag: Mapped[str | None] = mapped_column(String(30))
    below_pay_bar: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    years_required: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    visa_signal: Mapped[str | None] = mapped_column(String(30))  # sponsored|right_to_work_required|unknown
    salary_lpa: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))  # posted salary converted to ₹ LPA
    excluded: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    exclude_reason: Mapped[str | None] = mapped_column(Text)

    llm_score: Mapped[int | None] = mapped_column(SmallInteger)
    llm_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    llm_model: Mapped[str | None] = mapped_column(String(80))
    llm_content_hash: Mapped[str | None] = mapped_column(String(64))
    llm_scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    final_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    scored_at: Mapped[datetime] = _now_col()


class JobState(Base):
    __tablename__ = "job_state"

    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    # new | interested | applied | interviewing | offer | rejected | not_for_me
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="new")
    notes: Mapped[str | None] = mapped_column(Text)
    applied_on: Mapped[date | None] = mapped_column(Date)
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)  # schedule|manual|local
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="running")  # running|ok|partial|failed
    started_at: Mapped[datetime] = _now_col()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_s: Mapped[int | None] = mapped_column(Integer)
    companies_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    companies_ok: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    companies_failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    companies_manual: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    jobs_found: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    jobs_new: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    matches_new: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))


class CompanyRun(Base):
    __tablename__ = "company_runs"
    __table_args__ = (Index("ix_company_runs_company", "company_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # ok|failed|manual|skipped
    jobs_found: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    jobs_matched: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _now_col()


class TailoredResume(Base):
    """A resume tailored to one job by the dashboard (generated in web/, stored here for history)."""

    __tablename__ = "tailored_resumes"
    __table_args__ = (Index("ix_tailored_resumes_job", "job_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = _now_col()
    model: Mapped[str | None] = mapped_column(String(80))
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)  # the tailored resume (same shape as master)
    keywords: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)  # {must_have: [...], nice_to_have: [...]}
    score_before: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    score_after: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)  # matched, missing, gaps, checks, changes


class AppState(Base):
    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
