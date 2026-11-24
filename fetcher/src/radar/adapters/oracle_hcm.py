"""Oracle Recruiting Cloud (HCM) candidate experience sites.

cfg: {host: <xxx.fa.<dc>.oraclecloud.com>, site: <siteNumber e.g. CX_1>, search_terms?: [...],
      public_base?: url for job links (defaults to the hcmUI page)}
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from radar.adapters.base import Adapter, FetchContext, JobPosting, html_to_text, parse_datetime

PAGE = 25


class OracleHCM(Adapter):
    source_type = "oracle_hcm"
    needs_description_fetch = True

    def list_jobs(self, cfg: dict[str, Any], ctx: FetchContext) -> list[JobPosting]:
        host, site = cfg["host"], cfg["site"]
        terms = cfg.get("search_terms") or ctx.search_terms
        max_per_term = int(cfg.get("max_per_term", 200))
        seen: dict[str, JobPosting] = {}
        for term in terms:
            offset = 0
            while offset < max_per_term:
                finder = f'findReqs;siteNumber={site},limit={PAGE},offset={offset},keyword="{term}",sortBy=POSTING_DATES_DESC'
                url = (
                    f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
                    f"?onlyData=true&expand=requisitionList.secondaryLocations&finder={quote(finder, safe='=;,')}"
                )
                data = ctx.client.get_json(url)
                items = data.get("items") or [{}]
                reqs = items[0].get("requisitionList") or []
                for r in reqs:
                    rid = str(r.get("Id"))
                    if rid in seen:
                        continue
                    secondary = [s.get("Name") for s in r.get("secondaryLocations") or [] if s.get("Name")]
                    seen[rid] = JobPosting(
                        external_id=rid,
                        title=(r.get("Title") or "").strip(),
                        url=f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{rid}",
                        location=r.get("PrimaryLocation"),
                        locations=secondary,
                        country=r.get("PrimaryLocationCountry"),
                        is_remote="remote" in (r.get("WorkplaceType") or r.get("PrimaryLocation") or "").lower(),
                        posted_at=parse_datetime(r.get("PostedDate")),
                        description=r.get("ShortDescriptionStr"),
                    )
                offset += PAGE
                total = int(items[0].get("TotalJobsCount") or 0)
                if len(reqs) < PAGE or offset >= total:
                    break
        return list(seen.values())

    def fetch_description(self, job: JobPosting, cfg: dict[str, Any], ctx: FetchContext) -> str | None:
        finder = f'ById;Id="{job.external_id}",siteNumber={cfg["site"]}'
        url = (
            f"https://{cfg['host']}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
            f"?expand=all&onlyData=true&finder={quote(finder, safe='=;,')}"
        )
        data = ctx.client.get_json(url)
        items = data.get("items") or []
        if not items:
            return job.description
        d = items[0]
        parts = [
            html_to_text(d.get(k)) for k in ("ExternalDescriptionStr", "ExternalQualificationsStr", "ExternalResponsibilitiesStr")
        ]
        return "\n\n".join(p for p in parts if p) or job.description
