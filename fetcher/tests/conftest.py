"""Shared fixtures.

DB tests need a throwaway Postgres: set TEST_DATABASE_URL (e.g. the local docker DB
postgresql://radar:radar@localhost:5433/radar_test). They are skipped when it is unset.
"""

from __future__ import annotations

import os
from pathlib import Path

import openpyxl
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from radar.models import Base

HEADERS = [
    "#", "Company", "Priority", "Region", "Country", "Offices / Cities", "Company Type",
    "Why it fits you (AI / GenAI angle)", "Your Min Ask (₹ LPA)", "Pay vs Your Min (estimate)",
    "Visa Route (abroad)", "Careers Page", "Last Checked", "Status", "Notes",
]  # fmt: skip


def make_workbook(path: Path, rows: list[list]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Companies"
    ws.append(HEADERS)
    for r in rows:
        ws.append(r)
    wb.save(path)
    return path


def row(no: int, name: str, priority="P2 Strong", region="Chennai", country="India", url=None, min_ask=15):
    return [no, name, priority, region, country, "Chennai", "Product", "fit", min_ask, "Likely", "—",
            url or f"https://{name.lower().replace(' ', '')}.example.com/careers", None, "Not applied", None]  # fmt: skip


@pytest.fixture
def db_session():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    engine = create_engine(url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    Base.metadata.drop_all(engine)
    engine.dispose()
