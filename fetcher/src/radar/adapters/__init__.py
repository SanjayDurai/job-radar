"""Adapter registry: source_type (as used in config/companies.yaml) -> adapter instance."""

from __future__ import annotations

from radar.adapters.ats import Ashby, Greenhouse, Lever, Pinpoint, SmartRecruiters, Workable
from radar.adapters.base import Adapter, FetchContext, JobPosting
from radar.adapters.company_apis import (
    AmazonJobs,
    AtlassianListings,
    EightfoldPCSX,
    EmiratesGroup,
    GoogleCareers,
    Jibe,
    Mercari,
    PhonePe,
)
from radar.adapters.generic import HtmlLinks, PlaywrightLinks, Sitemap
from radar.adapters.oracle_hcm import OracleHCM
from radar.adapters.workday import Workday

_ADAPTERS: list[Adapter] = [
    EightfoldPCSX(),
    AmazonJobs(),
    AtlassianListings(),
    GoogleCareers(),
    EmiratesGroup(),
    PhonePe(),
    Mercari(),
    Jibe(),
    HtmlLinks(),
    Sitemap(),
    PlaywrightLinks(),
    Greenhouse(),
    Lever(),
    Ashby(),
    SmartRecruiters(),
    Workable(),
    Pinpoint(),
    Workday(),
    OracleHCM(),
]

REGISTRY: dict[str, Adapter] = {a.source_type: a for a in _ADAPTERS}


def get_adapter(source_type: str) -> Adapter | None:
    return REGISTRY.get(source_type)


__all__ = ["REGISTRY", "Adapter", "FetchContext", "JobPosting", "get_adapter"]
