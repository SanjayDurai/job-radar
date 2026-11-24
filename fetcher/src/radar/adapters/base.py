"""Adapter interface. Each adapter turns one source type (an ATS API, a company JSON endpoint,
or a browser-rendered page) into a list of `JobPosting`s.

Contract:
  list_jobs(cfg, ctx)        -> every currently open posting (title/location/url at minimum).
                                May include descriptions if the API returns them for free.
  fetch_description(job, cfg, ctx) -> full description text, called only for jobs that pass the
                                title/location pre-filter (keeps runs fast and polite).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar

from bs4 import BeautifulSoup

from radar.http import PoliteClient

# Default search terms for sources that need a keyword search instead of listing everything.
DEFAULT_SEARCH_TERMS = [
    "machine learning",
    "AI engineer",
    "artificial intelligence",
    "generative AI",
    "LLM",
    "data scientist",
    "applied scientist",
    "MLOps",
    "python",
    "software engineer",
]


@dataclass
class JobPosting:
    external_id: str
    title: str
    url: str
    location: str | None = None
    locations: list[str] = field(default_factory=list)
    country: str | None = None
    is_remote: bool = False
    department: str | None = None
    employment_type: str | None = None
    posted_at: datetime | None = None
    description: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None  # year | month | hour

    def all_locations_text(self) -> str:
        return " | ".join([x for x in [self.location, *self.locations, self.country] if x])


@dataclass
class FetchContext:
    client: PoliteClient
    search_terms: list[str] = field(default_factory=lambda: list(DEFAULT_SEARCH_TERMS))
    max_pages: int = 25


class Adapter:
    source_type: ClassVar[str]
    needs_description_fetch: ClassVar[bool] = False

    def list_jobs(self, cfg: dict[str, Any], ctx: FetchContext) -> list[JobPosting]:
        raise NotImplementedError

    def fetch_description(self, job: JobPosting, cfg: dict[str, Any], ctx: FetchContext) -> str | None:
        return job.description


# --- small helpers shared by adapters ------------------------------------------------------------


_BAD_CHARS = re.compile("[\x00\ud800-\udfff]")  # NUL bytes and lone surrogates (e.g. from broken JSON escapes)


def clean_text(value: str | None) -> str | None:
    """Make text safe to store in Postgres as UTF-8."""
    if value is None:
        return None
    return _BAD_CHARS.sub("", value).encode("utf-8", "replace").decode("utf-8")


def html_to_text(value: str | None) -> str | None:
    """HTML (possibly entity-escaped, as Greenhouse returns it) -> readable plain text."""
    if not value:
        return None
    if "&lt;" in value and "<" not in value:
        value = html.unescape(value)
    soup = BeautifulSoup(value, "html.parser")
    for br in soup.find_all(["br"]):
        br.replace_with("\n")
    for block in soup.find_all(["p", "li", "div", "h1", "h2", "h3", "h4", "tr"]):
        block.insert_after("\n")
    for li in soup.find_all("li"):
        li.insert_before("• ")
    text = soup.get_text()
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip() or None


def parse_datetime(value: Any) -> datetime | None:
    """Accept ISO strings, epoch seconds/milliseconds, or 'YYYY-MM-DD'."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, int | float):
            ts = value / 1000 if value > 10**11 else value
            return datetime.fromtimestamp(ts, tz=UTC)
        s = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (ValueError, OverflowError, OSError):
        return None


def join_url(base: str, path: str) -> str:
    if path.startswith("http"):
        return path
    return base.rstrip("/") + "/" + path.lstrip("/")
