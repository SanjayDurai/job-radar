"""Read the "Companies" sheet and sync it into the database + config/companies.yaml.

Re-running is safe: companies are matched by slug (or by careers URL if you renamed one),
existing job history is never touched, and companies removed from the sheet are marked
inactive instead of being deleted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.companies_config import load_companies_yaml, merge_sheet_into_yaml, save_companies_yaml
from radar.models import Company

SHEET_NAME = "Companies"

# Sheet header -> attribute name. Headers are matched case-insensitively by prefix,
# so small edits like "Why it fits you (AI / GenAI angle)" still work.
HEADER_MAP = {
    "#": "sheet_no",
    "company": "name",
    "priority": "priority_label",
    "region": "region_label",
    "country": "country",
    "offices": "cities",
    "company type": "company_type",
    "why it fits": "why_fit",
    "your min ask": "min_ask_lpa",
    "pay vs your min": "pay_vs_min",
    "visa route": "visa_route",
    "careers page": "careers_url",
    "status": "sheet_status",
    "notes": "sheet_notes",
}
REQUIRED = ("name", "priority_label", "region_label", "country", "careers_url")


class SheetError(ValueError):
    pass


@dataclass
class CompanyRow:
    name: str
    slug: str
    priority: int
    priority_label: str
    region: str
    region_label: str
    country: str
    careers_url: str
    sheet_no: int | None = None
    cities: str | None = None
    company_type: str | None = None
    why_fit: str | None = None
    min_ask_lpa: Decimal | None = None
    pay_vs_min: str | None = None
    visa_route: str | None = None
    sheet_status: str | None = None
    sheet_notes: str | None = None
    extra: dict = field(default_factory=dict)


def slugify(name: str) -> str:
    s = name.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:80]


def normalize_region(label: str) -> str:
    """Map the sheet's Region text to a fixed code."""
    s = label.lower()
    if s.strip() == "chennai":
        return "chennai"
    if s.startswith("india"):  # "India – Remote (...)" vs "India – Other city"
        return "india_remote" if "remote" in s else "india_other"
    if "abroad" in s:
        return "abroad"
    if s.startswith("remote"):  # "Remote (live in India)" = global remote company, work from India
        return "remote_global"
    raise SheetError(f"Unknown region {label!r}. Expected Chennai / India – Other city / India – Remote / Abroad / Remote.")


def parse_priority(label: str) -> int:
    m = re.search(r"P\s*([123])", label, re.IGNORECASE)
    if not m:
        raise SheetError(f"Unknown priority {label!r}. Expected 'P1 Dream', 'P2 Strong' or 'P3 Good'.")
    return int(m.group(1))


def _clean(value: object) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return None if s in ("", "—", "-") else s


def _map_headers(header_row: tuple) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for idx, raw in enumerate(header_row):
        if raw is None:
            continue
        h = str(raw).strip().lower()
        for prefix, attr in HEADER_MAP.items():
            if h == prefix or (prefix != "#" and h.startswith(prefix)):
                if attr not in mapping.values():
                    mapping[idx] = attr
                break
    missing = [a for a in REQUIRED if a not in mapping.values()]
    if missing:
        raise SheetError(f"Sheet is missing required columns: {missing}")
    return mapping


def read_companies(xlsx: Path) -> list[CompanyRow]:
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    if SHEET_NAME not in wb.sheetnames:
        raise SheetError(f"No sheet named {SHEET_NAME!r} in {xlsx.name}")
    rows = wb[SHEET_NAME].iter_rows(values_only=True)
    mapping = _map_headers(next(rows))

    out: list[CompanyRow] = []
    seen: set[str] = set()
    errors: list[str] = []
    for line_no, row in enumerate(rows, start=2):
        values = {attr: row[idx] if idx < len(row) else None for idx, attr in mapping.items()}
        name = _clean(values.get("name"))
        if not name:
            continue  # blank line
        try:
            careers_url = _clean(values.get("careers_url"))
            if not careers_url:
                raise SheetError("missing Careers Page URL")
            slug = slugify(name)
            if slug in seen:
                raise SheetError(f"duplicate company {name!r}")
            seen.add(slug)
            priority_label = _clean(values.get("priority_label")) or ""
            region_label = _clean(values.get("region_label")) or ""
            min_ask = values.get("min_ask_lpa")
            sheet_no = values.get("sheet_no")
            out.append(
                CompanyRow(
                    name=name,
                    slug=slug,
                    priority=parse_priority(priority_label),
                    priority_label=priority_label,
                    region=normalize_region(region_label),
                    region_label=region_label,
                    country=_clean(values.get("country")) or "",
                    careers_url=careers_url,
                    sheet_no=int(sheet_no) if isinstance(sheet_no, int | float) else None,
                    cities=_clean(values.get("cities")),
                    company_type=_clean(values.get("company_type")),
                    why_fit=_clean(values.get("why_fit")),
                    min_ask_lpa=Decimal(str(min_ask)) if isinstance(min_ask, int | float) else None,
                    pay_vs_min=_clean(values.get("pay_vs_min")),
                    visa_route=_clean(values.get("visa_route")),
                    sheet_status=_clean(values.get("sheet_status")),
                    sheet_notes=_clean(values.get("sheet_notes")),
                )
            )
        except SheetError as e:
            errors.append(f"row {line_no} ({name}): {e}")
    if errors:
        raise SheetError("Problems in the sheet:\n  " + "\n  ".join(errors))
    return out


SHEET_FIELDS = (
    "sheet_no", "name", "priority", "priority_label", "region", "region_label", "country", "cities",
    "company_type", "why_fit", "min_ask_lpa", "pay_vs_min", "visa_route", "careers_url",
    "sheet_status", "sheet_notes",
)  # fmt: skip


@dataclass
class SyncSummary:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: int = 0
    deactivated: list[str] = field(default_factory=list)
    reactivated: list[str] = field(default_factory=list)


def sync_companies(session: Session, rows: list[CompanyRow], yaml_entries: dict[str, dict]) -> SyncSummary:
    """Upsert sheet rows into `companies` and copy source_type/config from companies.yaml."""
    summary = SyncSummary()
    existing = {c.slug: c for c in session.scalars(select(Company))}
    by_url = {c.careers_url.rstrip("/").lower(): c for c in existing.values()}
    sheet_slugs: set[str] = set()

    for row in rows:
        company = existing.get(row.slug) or by_url.get(row.careers_url.rstrip("/").lower())
        cfg = yaml_entries.get(row.slug, {})
        if company is None:
            company = Company(slug=row.slug)
            session.add(company)
            summary.added.append(row.name)
            changed = True
        else:
            changed = False
            if company.slug != row.slug:  # renamed in the sheet
                company.slug = row.slug
                changed = True
            if not company.active:
                company.active = True
                summary.reactivated.append(row.name)
        for attr in SHEET_FIELDS:
            new = getattr(row, attr)
            if getattr(company, attr, None) != new:
                setattr(company, attr, new)
                changed = True
        source_type = cfg.get("source_type", "unknown")
        source_config = cfg.get("source_config") or {}
        if company.source_type != source_type or (company.source_config or {}) != source_config:
            company.source_type = source_type
            company.source_config = source_config
            changed = True
        if source_type == "manual" and company.health != "manual":
            company.health = "manual"
        sheet_slugs.add(row.slug)
        if changed and row.name not in summary.added:
            summary.updated.append(row.name)
        elif not changed:
            summary.unchanged += 1

    for slug, company in existing.items():
        if slug not in sheet_slugs and company.slug not in sheet_slugs and company.active:
            company.active = False
            summary.deactivated.append(company.name)
    return summary


def import_excel(session: Session, xlsx: Path) -> SyncSummary:
    rows = read_companies(xlsx)
    entries = merge_sheet_into_yaml(load_companies_yaml(), rows)
    save_companies_yaml(entries)
    return sync_companies(session, rows, entries)
