"""Adapters for company career sites with their own public JSON endpoints."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from radar.adapters.base import Adapter, FetchContext, JobPosting, html_to_text, join_url, parse_datetime


class EightfoldPCSX(Adapter):
    """Eightfold "PCSX" career sites (e.g. apply.careers.microsoft.com).

    cfg: {host, domain, location?: "India", search_terms?: [...], min_interval?: seconds, max_per_term?: int}
    """

    source_type = "eightfold"
    needs_description_fetch = True

    def list_jobs(self, cfg: dict[str, Any], ctx: FetchContext) -> list[JobPosting]:
        host, domain = cfg["host"], cfg["domain"]
        if cfg.get("min_interval"):
            ctx.client.set_host_interval(host, float(cfg["min_interval"]))
        max_per_term = int(cfg.get("max_per_term", 100))
        seen: dict[str, JobPosting] = {}
        for term in cfg.get("search_terms") or ctx.search_terms:
            start = 0
            while start < max_per_term:
                params = {"domain": domain, "query": term, "start": start}
                if cfg.get("location"):
                    params["location"] = cfg["location"]
                data = ctx.client.get_json(f"https://{host}/api/pcsx/search?{urlencode(params)}").get("data") or {}
                positions = data.get("positions") or []
                for p in positions:
                    pid = str(p["id"])
                    if pid in seen:
                        continue
                    seen[pid] = JobPosting(
                        external_id=pid,
                        title=(p.get("name") or "").strip(),
                        url=join_url(f"https://{host}", p.get("positionUrl") or f"/careers/job/{pid}"),
                        location=(p.get("locations") or [None])[0],
                        locations=(p.get("locations") or [])[1:],
                        is_remote=(p.get("workLocationOption") or "").lower() == "remote",
                        department=p.get("department"),
                        posted_at=parse_datetime(p.get("postedTs")),
                    )
                start += max(len(positions), 1)
                if not positions or start >= int(data.get("count") or 0):
                    break
        return list(seen.values())

    def fetch_description(self, job: JobPosting, cfg: dict[str, Any], ctx: FetchContext) -> str | None:
        params = urlencode({"position_id": job.external_id, "domain": cfg["domain"], "hl": "en"})
        data = ctx.client.get_json(f"https://{cfg['host']}/api/pcsx/position_details?{params}").get("data") or {}
        if data.get("publicUrl"):
            job.url = data["publicUrl"]
        return html_to_text(data.get("jobDescription"))


class AmazonJobs(Adapter):
    """amazon.jobs search.json.  cfg: {country: "IND", search_terms?: [...], max_per_term?: int}"""

    source_type = "amazon"

    def list_jobs(self, cfg: dict[str, Any], ctx: FetchContext) -> list[JobPosting]:
        max_per_term = int(cfg.get("max_per_term", 300))
        seen: dict[str, JobPosting] = {}
        for term in cfg.get("search_terms") or ctx.search_terms:
            offset = 0
            while offset < max_per_term:
                params = {"base_query": term, "result_limit": 100, "offset": offset, "sort": "recent"}
                if cfg.get("country"):
                    params["country"] = cfg["country"]
                data = ctx.client.get_json(f"https://www.amazon.jobs/en/search.json?{urlencode(params)}")
                jobs = data.get("jobs") or []
                for j in jobs:
                    jid = str(j.get("id_icims") or j.get("id"))
                    if jid in seen:
                        continue
                    desc = "\n\n".join(
                        f"{label}\n{html_to_text(j.get(k))}"
                        for label, k in (("Description", "description"), ("Basic qualifications", "basic_qualifications"),
                                         ("Preferred qualifications", "preferred_qualifications"))
                        if j.get(k)
                    )  # fmt: skip
                    seen[jid] = JobPosting(
                        external_id=jid,
                        title=(j.get("title") or "").strip(),
                        url=join_url("https://www.amazon.jobs", j.get("job_path") or f"/en/jobs/{jid}"),
                        location=j.get("normalized_location") or j.get("location"),
                        country=j.get("country_code"),
                        department=j.get("job_category") or j.get("business_category"),
                        employment_type=j.get("job_schedule_type"),
                        posted_at=_parse_us_date(j.get("posted_date")),
                        description=desc or None,
                    )
                offset += 100
                if len(jobs) < 100 or offset >= int(data.get("hits") or 0):
                    break
        return list(seen.values())


class AtlassianListings(Adapter):
    """atlassian.com/endpoint/careers/listings: one JSON array with every posting + description."""

    source_type = "atlassian"

    def list_jobs(self, cfg: dict[str, Any], ctx: FetchContext) -> list[JobPosting]:
        data = ctx.client.get_json("https://www.atlassian.com/endpoint/careers/listings")
        jobs = []
        for j in data:
            locs = [re.sub(r"\s+", " ", x).strip() for x in j.get("locations") or []]
            portal = j.get("portalJobPost") or {}
            desc = "\n\n".join(
                t for t in (html_to_text(j.get(k)) for k in ("overview", "responsibilities", "qualifications")) if t
            )
            jobs.append(
                JobPosting(
                    external_id=str(j["id"]),
                    title=(j.get("title") or "").strip(),
                    url=portal.get("portalUrl") or f"https://www.atlassian.com/company/careers/details/{j['id']}",
                    location=locs[0] if locs else None,
                    locations=locs[1:],
                    is_remote=any("remote" in x.lower() for x in locs),
                    department=j.get("category"),
                    posted_at=_parse_atlassian_date(portal.get("updatedDate")),
                    description=desc or None,
                )
            )
        return jobs


class GoogleCareers(Adapter):
    """google.com/about/careers results pages (allowed by robots.txt). Each results page embeds the
    job data (title, description, locations) as JSON-ish arrays.

    cfg: {location: "India", search_terms?: [...], pages?: 3}
    """

    source_type = "google"
    ID_TITLE = re.compile(
        r'\["(\d{15,20})","((?:[^"\\]|\\.){3,200})","https://www\.google\.com/about/careers/applications/signin'
    )
    HTML_BLOB = re.compile(r'\[null,("(?:[^"\\]|\\.)*")\]')
    PLACE = re.compile(r'"([A-Z][^"\\,\[\]]{1,40}(?:, [A-Z][^"\\,\[\]]{1,40}){1,2})"')

    def list_jobs(self, cfg: dict[str, Any], ctx: FetchContext) -> list[JobPosting]:
        jobs: dict[str, JobPosting] = {}
        for term in cfg.get("search_terms") or ctx.search_terms:
            for page in range(1, int(cfg.get("pages", 3)) + 1):
                params: dict[str, Any] = {"q": term}
                if cfg.get("location"):
                    params["location"] = cfg["location"]
                if page > 1:
                    params["page"] = page
                url = f"https://www.google.com/about/careers/applications/jobs/results/?{urlencode(params)}"
                if page > 1 and not ctx.client.allowed(url):
                    break  # robots.txt allows only the first results page per search
                html = ctx.client.get(url, headers={"Accept": "text/html"}).text
                matches = list(self.ID_TITLE.finditer(html))
                if not matches:
                    break
                for i, m in enumerate(matches):
                    jid = m.group(1)
                    chunk = html[m.end() : matches[i + 1].start() if i + 1 < len(matches) else m.end() + 20000]
                    if jid in jobs:
                        continue
                    title = _json_str(m.group(2))
                    blobs = [html_to_text(_json_str(b)) for b in self.HTML_BLOB.findall(chunk)[:4]]
                    places = [p for p in dict.fromkeys(self.PLACE.findall(chunk)) if p != title][:5]
                    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
                    jobs[jid] = JobPosting(
                        external_id=jid,
                        title=title,
                        url=f"https://www.google.com/about/careers/applications/jobs/results/{jid}-{slug}",
                        location=places[0] if places else cfg.get("location"),
                        locations=places[1:],
                        description="\n\n".join(b for b in blobs if b) or None,
                    )
        return list(jobs.values())


class PhonePe(Adapter):
    """phonepe.com/apollo/job-postings/latest.json — keeps only status PUBLIC postings."""

    source_type = "phonepe"

    def list_jobs(self, cfg: dict[str, Any], ctx: FetchContext) -> list[JobPosting]:
        data = ctx.client.get_json("https://www.phonepe.com/apollo/job-postings/latest.json")
        jobs = []
        for j in data.get("results", []):
            if j.get("status") != "PUBLIC":
                continue
            ms = re.search(r"\d+", str(j.get("updatedAt") or ""))
            key = f"{j.get('title', '')}|{j.get('location', '')}|{j.get('department', '')}"
            jobs.append(
                JobPosting(
                    external_id=hashlib.sha1(key.encode()).hexdigest()[:16],
                    title=(j.get("title") or "").strip(),
                    url=j.get("applyUrl") or "https://www.phonepe.com/careers/job-openings/",
                    location=j.get("location"),
                    country="India",
                    department=j.get("department"),
                    employment_type=j.get("type"),
                    posted_at=parse_datetime(int(ms.group(0))) if ms else None,
                )
            )
        return jobs


class Mercari(Adapter):
    """careers.mercari.com/api/jobs (their site's own GraphQL-backed JSON; postings live on Workable)."""

    source_type = "mercari"
    needs_description_fetch = True

    def list_jobs(self, cfg: dict[str, Any], ctx: FetchContext) -> list[JobPosting]:
        data = ctx.client.get_json("https://careers.mercari.com/api/jobs/?keyword=")
        nodes = (((data.get("data") or {}).get("jobs") or {}).get("nodes")) or []
        jobs = []
        for n in nodes:
            locs = [x.get("slug", "").replace("-", " ").title() for x in (n.get("locations") or {}).get("nodes", [])]
            jobs.append(
                JobPosting(
                    external_id=n.get("slug") or n["id"],
                    title=(n.get("title") or "").strip(),
                    url=f"https://careers.mercari.com/en/jobs/{n.get('slug')}/",
                    location=", ".join(locs) + ", Japan" if locs else "Japan",
                    country="Japan",
                )
            )
        return jobs

    def fetch_description(self, job: JobPosting, cfg: dict[str, Any], ctx: FetchContext) -> str | None:
        from radar.adapters.generic import enrich_from_detail_page

        r = ctx.client.get(job.url, headers={"Accept": "text/html"})
        return enrich_from_detail_page(job, r.text) if r.status_code < 400 else None


class Jibe(Adapter):
    """iCIMS "Jibe" career sites (e.g. jobs.booking.com):  GET {base}/api/jobs?page=&limit=&keywords=

    cfg: {base: "https://jobs.booking.com", search_terms?: [...]}
    """

    source_type = "jibe"

    def list_jobs(self, cfg: dict[str, Any], ctx: FetchContext) -> list[JobPosting]:
        base = cfg["base"].rstrip("/")
        jobs: dict[str, JobPosting] = {}
        for term in cfg.get("search_terms") or ctx.search_terms:
            for page in range(1, ctx.max_pages + 1):
                data = ctx.client.get_json(f"{base}/api/jobs?{urlencode({'page': page, 'limit': 100, 'keywords': term})}")
                items = data.get("jobs") or []
                for item in items:
                    j = item.get("data") or {}
                    jid = str(j.get("req_id") or j.get("slug"))
                    if jid in jobs:
                        continue
                    locs = [x for x in [j.get("full_location"), j.get("location_name")] if x]
                    jobs[jid] = JobPosting(
                        external_id=jid,
                        title=(j.get("title") or "").strip(),
                        url=j.get("apply_url") if not j.get("slug") else f"{base}/{cfg.get('path', 'booking')}/jobs/{j['slug']}",
                        location=locs[0] if locs else None,
                        country=j.get("country"),
                        department=", ".join(j.get("categories", [{}])[0].values()) if j.get("categories") else None,
                        employment_type=j.get("employment_type"),
                        posted_at=parse_datetime(j.get("posted_date") or j.get("create_date")),
                        description=html_to_text(j.get("description")),
                        is_remote="remote" in str(j.get("location_type", "")).lower(),
                    )
                if len(items) < 100 or page * 100 >= int(data.get("totalCount") or 0):
                    break
        return list(jobs.values())


class EmiratesGroup(Adapter):
    """emiratesgroupcareers.com/api/v1/jobs (the site's own JSON; robots.txt only blocks search-page params)."""

    source_type = "emirates"

    def list_jobs(self, cfg: dict[str, Any], ctx: FetchContext) -> list[JobPosting]:
        data = ctx.client.get_json(
            "https://www.emiratesgroupcareers.com/api/v1/jobs?title=&brand=&category=&location=&jobcategory=&showAll=true"
        )
        jobs = []
        for j in data.get("data") or []:
            rid = str(j.get("reqid") or j.get("reqno"))
            loc = ", ".join(x for x in [j.get("city"), j.get("state"), j.get("country")] if x) or j.get("location")
            jobs.append(
                JobPosting(
                    external_id=rid,
                    title=(j.get("title") or "").strip(),
                    url=j.get("joburl") or j.get("applyurl") or f"https://www.emiratesgroupcareers.com/search-and-apply/{rid}",
                    location=loc,
                    country=j.get("country"),
                    department=j.get("category") or j.get("brand"),
                    posted_at=parse_datetime(j.get("postingdate")),
                    description=html_to_text(j.get("jobdescription")),
                )
            )
        return jobs


def _json_str(raw: str) -> str:
    import json

    try:
        return json.loads(raw if raw.startswith('"') else f'"{raw}"')
    except ValueError:
        return raw


def _parse_us_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%B %d, %Y").replace(tzinfo=datetime.now().astimezone().tzinfo)
    except ValueError:
        return parse_datetime(value)


def _parse_atlassian_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %I:%M %p").astimezone()
    except ValueError:
        return None
