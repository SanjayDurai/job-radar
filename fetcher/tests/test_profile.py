from datetime import date

from radar.profile import experience_years, parse_year_month


def test_parse_year_month():
    assert parse_year_month("2025-08") == date(2025, 8, 1)
    assert parse_year_month(date(2025, 8, 17)) == date(2025, 8, 1)


def test_experience_years_matches_profile_today():
    # Aug 2025 -> Nov 2026 inclusive = 16 months
    assert experience_years(today=date(2026, 11, 23), career_start="2025-08") == 1.3


def test_experience_grows_over_time():
    assert experience_years(today=date(2027, 7, 1), career_start="2025-08") == 2.0
    assert experience_years(today=date(2025, 8, 5), career_start="2025-08") == 0.1


def test_experience_reads_config():
    assert experience_years(today=date(2026, 11, 1)) > 1.0
