from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

import pytest
from conftest import make_workbook, row
from sqlalchemy import select

from radar.companies_config import merge_sheet_into_yaml
from radar.excel_import import (
    SheetError,
    normalize_region,
    parse_priority,
    read_companies,
    slugify,
    sync_companies,
)
from radar.models import Company, Job
from radar.settings import DEFAULT_XLSX


@pytest.mark.parametrize(
    "label,code",
    [
        ("Chennai", "chennai"),
        ("India – Other city", "india_other"),
        ("India – Remote (can stay in Chennai)", "india_remote"),
        ("Abroad", "abroad"),
        ("Remote (live in India)", "remote_global"),
    ],
)
def test_normalize_region(label, code):
    assert normalize_region(label) == code


def test_normalize_region_unknown():
    with pytest.raises(SheetError):
        normalize_region("Mars")


def test_parse_priority():
    assert parse_priority("P1 Dream") == 1
    assert parse_priority("p3 good") == 3
    with pytest.raises(SheetError):
        parse_priority("Dream")


def test_slugify():
    assert slugify("Eternal (Zomato / Blinkit)") == "eternal-zomato-blinkit"
    assert slugify("Ford Global Technology & Business Center") == "ford-global-technology-and-business-center"


def test_real_workbook_parses():
    rows = read_companies(DEFAULT_XLSX)
    assert len(rows) == 100
    assert len({r.slug for r in rows}) == 100
    regions = Counter(r.region for r in rows)
    assert regions == {"abroad": 38, "india_other": 37, "chennai": 20, "remote_global": 4, "india_remote": 1}
    assert all(r.careers_url.startswith("https://") for r in rows)


def test_sheet_errors_are_collected(tmp_path):
    xlsx = make_workbook(tmp_path / "bad.xlsx", [row(1, "A", region="Mars"), row(2, "B", priority="??")])
    with pytest.raises(SheetError) as e:
        read_companies(xlsx)
    assert "row 2 (A)" in str(e.value) and "row 3 (B)" in str(e.value)


def test_blank_rows_skipped(tmp_path):
    xlsx = make_workbook(tmp_path / "ok.xlsx", [row(1, "Alpha"), [None] * 15, row(2, "Beta")])
    assert [r.name for r in read_companies(xlsx)] == ["Alpha", "Beta"]


def test_yaml_merge_keeps_source_settings_and_flags_removed(tmp_path):
    rows = read_companies(make_workbook(tmp_path / "a.xlsx", [row(1, "Alpha"), row(2, "Beta")]))
    entries = merge_sheet_into_yaml({}, rows)
    entries["alpha"]["source_type"] = "greenhouse"
    entries["alpha"]["source_config"] = {"board": "alpha"}

    rows2 = read_companies(make_workbook(tmp_path / "b.xlsx", [row(1, "Alpha"), row(3, "Gamma")]))
    merged = merge_sheet_into_yaml(entries, rows2)
    assert merged["alpha"]["source_type"] == "greenhouse"
    assert merged["alpha"]["source_config"] == {"board": "alpha"}
    assert merged["gamma"]["source_type"] == "unknown"
    assert merged["beta"]["in_sheet"] is False


# --- database sync (needs TEST_DATABASE_URL) ---------------------------------------------


def test_sync_reimport_keeps_job_history(db_session, tmp_path):
    rows = read_companies(make_workbook(tmp_path / "a.xlsx", [row(1, "Alpha"), row(2, "Beta")]))
    summary = sync_companies(db_session, rows, merge_sheet_into_yaml({}, rows))
    db_session.commit()
    assert sorted(summary.added) == ["Alpha", "Beta"]

    beta = db_session.scalar(select(Company).where(Company.slug == "beta"))
    db_session.add(Job(company_id=beta.id, external_key="1", title="ML Engineer", url="https://x/1",
                       first_seen=datetime.now(UTC)))  # fmt: skip
    db_session.commit()

    # Beta removed, Alpha's priority changed, Gamma added
    rows2 = read_companies(make_workbook(tmp_path / "b.xlsx", [row(1, "Alpha", priority="P1 Dream"), row(3, "Gamma")]))
    summary2 = sync_companies(db_session, rows2, merge_sheet_into_yaml({}, rows2))
    db_session.commit()
    assert summary2.added == ["Gamma"]
    assert summary2.updated == ["Alpha"]
    assert summary2.deactivated == ["Beta"]

    beta = db_session.scalar(select(Company).where(Company.slug == "beta"))
    assert beta.active is False
    assert db_session.scalar(select(Job).where(Job.company_id == beta.id)) is not None  # history kept

    # Running the same import again changes nothing
    summary3 = sync_companies(db_session, rows2, merge_sheet_into_yaml({}, rows2))
    assert summary3.added == summary3.updated == summary3.deactivated == []
    assert summary3.unchanged == 2


def test_sync_rename_matches_by_url(db_session, tmp_path):
    url = "https://alpha.example.com/careers"
    rows = read_companies(make_workbook(tmp_path / "a.xlsx", [row(1, "Alpha", url=url)]))
    sync_companies(db_session, rows, {})
    db_session.commit()
    first_id = db_session.scalar(select(Company.id))

    rows2 = read_companies(make_workbook(tmp_path / "b.xlsx", [row(1, "Alpha Labs", url=url)]))
    summary = sync_companies(db_session, rows2, {})
    db_session.commit()
    assert summary.added == [] and summary.updated == ["Alpha Labs"]
    company = db_session.scalar(select(Company))
    assert (company.id, company.slug) == (first_id, "alpha-labs")


def test_sync_copies_source_from_yaml(db_session, tmp_path):
    rows = read_companies(make_workbook(tmp_path / "a.xlsx", [row(1, "Alpha")]))
    entries = merge_sheet_into_yaml({}, rows)
    entries["alpha"].update(source_type="manual", notes="no public listing")
    sync_companies(db_session, rows, entries)
    db_session.commit()
    company = db_session.scalar(select(Company))
    assert company.source_type == "manual" and company.health == "manual"


def test_master_resume_validation():
    from radar.resume import ResumeError, validate_master

    good = {
        "basics": {"name": "A", "email": "a@b.c"},
        "skills": {"Core": ["Python"]},
        "experience": [{"id": "x", "bullets": [{"id": "x1", "text": "Did a thing"}]}],
        "projects": [{"id": "p", "bullets": [{"id": "p1", "text": "Built"}]}],
    }
    validate_master(good)
    bad = {**good, "projects": [{"id": "p", "bullets": [{"id": "x1", "text": "dup"}, {"text": "no id"}]}]}
    with pytest.raises(ResumeError) as e:
        validate_master(bad)
    assert "duplicate bullet id 'x1'" in str(e.value) and "needs an id and text" in str(e.value)
