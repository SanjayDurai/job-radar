"""Adapters for ATS platforms with public, documented-ish JSON job board APIs."""

from __future__ import annotations

from typing import Any

from radar.adapters.base import Adapter, FetchContext, JobPosting, html_to_text, parse_datetime


class Greenhouse(Adapter):
    """cfg: {board: <token>}  — boards-api.greenhouse.io (descriptions included)."""

    source_type = "greenhouse"

    def list_jobs(self, cfg: dict[str, Any], ctx: FetchContext) -> list[JobPosting]:
        data = ctx.client.get_json(f"https://boards-api.greenhouse.io/v1/boards/{cfg['board']}/jobs?content=true")
        jobs = []
        for j in data.get("jobs", []):
            offices = [o.get("location") or o.get("name") for o in j.get("offices") or [] if o]
            loc = (j.get("location") or {}).get("name")
            jobs.append(
                JobPosting(
                    external_id=str(j["id"]),
                    title=j.get("title", "").strip(),
                    url=j.get("absolute_url"),
                    location=loc,
                    locations=[o for o in offices if o and o != loc],
                    is_remote="remote" in (loc or "").lower(),
                    department=", ".join(d["name"] for d in j.get("departments") or [] if d.get("name")) or None,
                    posted_at=parse_datetime(j.get("first_published") or j.get("updated_at")),
                    description=html_to_text(j.get("content")),
                )
            )
        return jobs


class Lever(Adapter):
    """cfg: {company: <slug>, eu: bool}  — api.lever.co (descriptions included)."""

    source_type = "lever"

    def list_jobs(self, cfg: dict[str, Any], ctx: FetchContext) -> list[JobPosting]:
        host = "api.eu.lever.co" if cfg.get("eu") else "api.lever.co"
        data = ctx.client.get_json(f"https://{host}/v0/postings/{cfg['company']}?mode=json")
        jobs = []
        for j in data:
            cat = j.get("categories") or {}
            parts = [j.get("descriptionPlain") or ""]
            for lst in j.get("lists") or []:
                parts.append(f"{lst.get('text', '')}\n{html_to_text(lst.get('content')) or ''}")
            parts.append(j.get("additionalPlain") or "")
            salary = j.get("salaryRange") or {}
            jobs.append(
                JobPosting(
                    external_id=j["id"],
                    title=(j.get("text") or "").strip(),
                    url=j.get("hostedUrl"),
                    location=cat.get("location"),
                    locations=[x for x in cat.get("allLocations") or [] if x != cat.get("location")],
                    country=j.get("country"),
                    is_remote=(j.get("workplaceType") == "remote") or "remote" in (cat.get("location") or "").lower(),
                    department=cat.get("team") or cat.get("department"),
                    employment_type=cat.get("commitment"),
                    posted_at=parse_datetime(j.get("createdAt")),
                    description="\n\n".join(p.strip() for p in parts if p and p.strip()) or None,
                    salary_min=salary.get("min"),
                    salary_max=salary.get("max"),
                    salary_currency=salary.get("currency"),
                    salary_period=_period(salary.get("interval")),
                )
            )
        return jobs


class Ashby(Adapter):
    """cfg: {board: <name>}  — api.ashbyhq.com posting API (descriptions + compensation included)."""

    source_type = "ashby"

    def list_jobs(self, cfg: dict[str, Any], ctx: FetchContext) -> list[JobPosting]:
        data = ctx.client.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{cfg['board']}?includeCompensation=true")
        jobs = []
        for j in data.get("jobs", []):
            if j.get("isListed") is False:
                continue
            secondary = [s.get("location") for s in j.get("secondaryLocations") or [] if s.get("location")]
            addr = ((j.get("address") or {}).get("postalAddress") or {}).get("addressCountry")
            sal = _ashby_salary(j.get("compensation") or {})
            jobs.append(
                JobPosting(
                    external_id=j["id"],
                    title=(j.get("title") or "").strip(),
                    url=j.get("jobUrl"),
                    location=j.get("location"),
                    locations=secondary,
                    country=addr,
                    is_remote=bool(j.get("isRemote")) or j.get("workplaceType") == "Remote",
                    department=j.get("department") or j.get("team"),
                    employment_type=j.get("employmentType"),
                    posted_at=parse_datetime(j.get("publishedAt")),
                    description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
                    **sal,
                )
            )
        return jobs


class SmartRecruiters(Adapter):
    """cfg: {company: <id>}  — api.smartrecruiters.com. Listing has no description; fetched per job."""

    source_type = "smartrecruiters"
    needs_description_fetch = True

    def list_jobs(self, cfg: dict[str, Any], ctx: FetchContext) -> list[JobPosting]:
        company = cfg["company"]
        jobs: list[JobPosting] = []
        offset, limit = 0, 100
        for _ in range(ctx.max_pages):
            data = ctx.client.get_json(
                f"https://api.smartrecruiters.com/v1/companies/{company}/postings?limit={limit}&offset={offset}"
            )
            for j in data.get("content", []):
                loc = j.get("location") or {}
                jobs.append(
                    JobPosting(
                        external_id=str(j["id"]),
                        title=(j.get("name") or "").strip(),
                        url=f"https://jobs.smartrecruiters.com/{company}/{j['id']}",
                        location=loc.get("fullLocation") or ", ".join(x for x in [loc.get("city"), loc.get("country")] if x),
                        country=(loc.get("country") or "").upper() or None,
                        is_remote=bool(loc.get("remote")),
                        department=(j.get("department") or {}).get("label"),
                        employment_type=(j.get("typeOfEmployment") or {}).get("label"),
                        posted_at=parse_datetime(j.get("releasedDate")),
                    )
                )
            offset += limit
            if offset >= int(data.get("totalFound", 0)):
                break
        return jobs

    def fetch_description(self, job: JobPosting, cfg: dict[str, Any], ctx: FetchContext) -> str | None:
        data = ctx.client.get_json(f"https://api.smartrecruiters.com/v1/companies/{cfg['company']}/postings/{job.external_id}")
        sections = ((data.get("jobAd") or {}).get("sections")) or {}
        parts = [
            f"{s.get('title', '')}\n{html_to_text(s.get('text')) or ''}"
            for key in ("jobDescription", "qualifications", "additionalInformation")
            if (s := sections.get(key))
        ]
        if data.get("postingUrl"):
            job.url = data["postingUrl"]
        return "\n\n".join(parts) or None


class Workable(Adapter):
    """cfg: {account: <name>}  — apply.workable.com v3 listing, v2 detail."""

    source_type = "workable"
    needs_description_fetch = True

    def list_jobs(self, cfg: dict[str, Any], ctx: FetchContext) -> list[JobPosting]:
        account = cfg["account"]
        url = f"https://apply.workable.com/api/v3/accounts/{account}/jobs"
        jobs: list[JobPosting] = []
        body: dict[str, Any] = {}
        for _ in range(ctx.max_pages):
            data = ctx.client.post_json(url, json=body)
            for j in data.get("results", []):
                loc = j.get("location") or {}
                locs = [", ".join(x for x in [lc.get("city"), lc.get("country")] if x) for lc in j.get("locations") or []]
                jobs.append(
                    JobPosting(
                        external_id=j["shortcode"],
                        title=(j.get("title") or "").strip(),
                        url=f"https://apply.workable.com/{account}/j/{j['shortcode']}/",
                        location=", ".join(x for x in [loc.get("city"), loc.get("region"), loc.get("country")] if x) or None,
                        locations=[x for x in locs if x],
                        country=loc.get("country"),
                        is_remote=bool(j.get("remote")) or j.get("workplace") == "remote",
                        department=", ".join(j.get("department") or [])
                        if isinstance(j.get("department"), list)
                        else j.get("department"),
                        employment_type=j.get("type"),
                        posted_at=parse_datetime(j.get("published")),
                    )
                )
            token = data.get("nextPage")
            if not token:
                break
            body = {"token": token}
        return jobs

    def fetch_description(self, job: JobPosting, cfg: dict[str, Any], ctx: FetchContext) -> str | None:
        data = ctx.client.get_json(f"https://apply.workable.com/api/v2/accounts/{cfg['account']}/jobs/{job.external_id}")
        parts = [html_to_text(data.get(k)) for k in ("description", "requirements", "benefits")]
        return "\n\n".join(p for p in parts if p) or None


class Pinpoint(Adapter):
    """cfg: {subdomain: <name>}  — <subdomain>.pinpointhq.com/postings.json (descriptions included)."""

    source_type = "pinpoint"

    def list_jobs(self, cfg: dict[str, Any], ctx: FetchContext) -> list[JobPosting]:
        data = ctx.client.get_json(f"https://{cfg['subdomain']}.pinpointhq.com/postings.json")
        jobs = []
        for j in data.get("data", []):
            loc = j.get("location") or {}
            comp_min, comp_max = j.get("compensation_minimum"), j.get("compensation_maximum")
            desc = "\n\n".join(
                t
                for t in (html_to_text(j.get(k)) for k in ("description", "key_responsibilities", "skills_knowledge_expertise"))
                if t
            )
            jobs.append(
                JobPosting(
                    external_id=str(j["id"]),
                    title=(j.get("title") or "").strip(),
                    url=j.get("url"),
                    location=loc.get("name") or loc.get("city"),
                    is_remote=(j.get("workplace_type") or "").lower() == "remote",
                    department=(j.get("department") or {}).get("name") if isinstance(j.get("department"), dict) else None,
                    employment_type=j.get("employment_type_text") or j.get("employment_type"),
                    description=desc or None,
                    salary_min=float(comp_min) if comp_min else None,
                    salary_max=float(comp_max) if comp_max else None,
                    salary_currency=j.get("compensation_currency"),
                    salary_period=_period(j.get("compensation_frequency")),
                )
            )
        return jobs


# --- helpers ---------------------------------------------------------------------------------------


def _period(value: Any) -> str | None:
    v = str(value or "").lower()
    if not v:
        return None
    if "hour" in v:
        return "hour"
    if "month" in v:
        return "month"
    if "year" in v or "annual" in v:
        return "year"
    return None


def _ashby_salary(comp: dict[str, Any]) -> dict[str, Any]:
    for tier in comp.get("summaryComponents") or []:
        if tier.get("compensationType") == "Salary":
            return {
                "salary_min": tier.get("minValue"),
                "salary_max": tier.get("maxValue"),
                "salary_currency": tier.get("currencyCode"),
                "salary_period": _period(tier.get("interval")),
            }
    return {}
