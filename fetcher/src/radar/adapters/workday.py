"""Workday career sites: POST https://{host}/wday/cxs/{tenant}/{site}/jobs

cfg: {host, tenant, site, search_terms?: [...], applied_facets?: {...}, max_per_term?: int}
Large tenants have thousands of postings, so we search by keyword (configurable) and dedupe.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from radar.adapters.base import Adapter, FetchContext, JobPosting, html_to_text, parse_datetime

PAGE = 20  # Workday rejects larger page sizes
MULTI_LOCATION = re.compile(r"^\s*\d+\s+locations?\s*$", re.I)

# Workday search is full-text and broad, so a few terms cover the target roles. Fewer requests
# keeps us well under Workday's per-IP rate limit, which is shared across all its customers' sites.
WORKDAY_TERMS = ["machine learning", "artificial intelligence", "data scientist", "applied scientist", "LLM", "software engineer"]


def parse_posted_on(text: str | None, now: datetime | None = None) -> datetime | None:
    """'Posted Today' / 'Posted Yesterday' / 'Posted 3 Days Ago' / 'Posted 30+ Days Ago'."""
    if not text:
        return None
    now = now or datetime.now(UTC)
    t = text.lower()
    if "today" in t:
        return now
    if "yesterday" in t:
        return now - timedelta(days=1)
    m = re.search(r"(\d+)\+?\s*day", t)
    return now - timedelta(days=int(m.group(1))) if m else None


class Workday(Adapter):
    source_type = "workday"
    needs_description_fetch = True

    def _base(self, cfg: dict[str, Any]) -> str:
        return f"https://{cfg['host']}/wday/cxs/{cfg['tenant']}/{cfg['site']}"

    def list_jobs(self, cfg: dict[str, Any], ctx: FetchContext) -> list[JobPosting]:
        # Paced across ALL *.myworkdayjobs.com sites together (see radar.http.rate_bucket)
        ctx.client.set_host_interval(cfg["host"], float(cfg.get("min_interval", 1.5)))
        url = self._base(cfg) + "/jobs"
        terms = cfg.get("search_terms") or WORKDAY_TERMS
        max_per_term = int(cfg.get("max_per_term", 100))
        seen: dict[str, JobPosting] = {}
        for term in terms:
            offset = 0
            while offset < max_per_term:
                body = {"appliedFacets": cfg.get("applied_facets", {}), "limit": PAGE, "offset": offset, "searchText": term}
                data = ctx.client.post_json(url, json=body, headers={"Content-Type": "application/json"})
                postings = data.get("jobPostings") or []
                for p in postings:
                    path = p.get("externalPath")
                    if not path or path in seen:
                        continue
                    loc_text = p.get("locationsText") or ""
                    seen[path] = JobPosting(
                        external_id=path.rsplit("/", 1)[-1],
                        title=(p.get("title") or "").strip(),
                        url=f"https://{cfg['host']}/en-US/{cfg['site']}{path}",
                        # "3 Locations" says nothing: leave it unknown so the detail page decides
                        location=None if MULTI_LOCATION.match(loc_text) else (loc_text or None),
                        is_remote="remote" in loc_text.lower(),
                        posted_at=parse_posted_on(p.get("postedOn")),
                    )
                offset += PAGE
                if len(postings) < PAGE or offset >= int(data.get("total") or 0):
                    break
        return list(seen.values())

    def fetch_description(self, job: JobPosting, cfg: dict[str, Any], ctx: FetchContext) -> str | None:
        path = job.url.split(f"/{cfg['site']}", 1)[-1]
        data = ctx.client.get_json(self._base(cfg) + path)
        info = data.get("jobPostingInfo") or {}
        if info.get("location"):
            extra = [x for x in info.get("additionalLocations") or [] if x]
            job.locations = [info["location"], *extra]
        if info.get("country"):
            job.country = (info["country"] or {}).get("descriptor") if isinstance(info["country"], dict) else info["country"]
        job.employment_type = info.get("timeType") or job.employment_type
        job.posted_at = parse_datetime(info.get("startDate")) or job.posted_at
        if info.get("externalUrl"):
            job.url = info["externalUrl"]
        return html_to_text(info.get("jobDescription"))
