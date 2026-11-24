"""Helpers derived from config/profile.yaml."""

from __future__ import annotations

from datetime import date

from radar.settings import profile


def parse_year_month(value: str | date) -> date:
    """Accept '2025-08', a date, or a YAML-parsed date and return the first of that month."""
    if isinstance(value, date):
        return value.replace(day=1)
    year, month = str(value).strip().split("-")[:2]
    return date(int(year), int(month), 1)


def experience_years(today: date | None = None, career_start: str | date | None = None) -> float:
    """Years of experience since `career_start`, rounded to one decimal (e.g. 1.3)."""
    start = parse_year_month(career_start if career_start is not None else profile()["career_start"])
    today = today or date.today()
    # Inclusive of the start month: Aug 2025 -> Nov 2026 counts as 16 months (1.3 years)
    months = (today.year - start.year) * 12 + (today.month - start.month) + 1
    return round(max(months, 0) / 12, 1)
