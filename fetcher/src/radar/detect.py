"""Detect which ATS / job source each company uses, and verify it against the live endpoint.

Steps per company:
  1. GET the careers URL (following redirects) and scan the final URL + HTML for ATS fingerprints.
  2. If nothing is found, follow up to 3 "jobs / openings / search" links one hop deep and scan again.
  3. If still nothing, probe the simple public ATS APIs with name-based board guesses.
  4. Verify every candidate that has a simple public API (count open jobs).

Results go to config/detect_report.json and (for companies still `unknown`) config/companies.yaml.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from radar.http import FetchError, PoliteClient, RobotsDisallowed
from radar.settings import CONFIG_DIR

TOKEN = r"([A-Za-z0-9][\w.-]*[A-Za-z0-9])"
BAD_TOKENS = {"embed", "js", "job_board", "jobs", "api", "v1", "boards", "en", "www", "careers", "static", "assets"}

# (source_type, regex, function(match) -> source_config)
SIGNATURES: list[tuple[str, re.Pattern[str], Any]] = [
    ("greenhouse", re.compile(r"boards-api\.greenhouse\.io/v1/boards/" + TOKEN), lambda m: {"board": m.group(1)}),
    ("greenhouse", re.compile(r"greenhouse\.io/embed/job_board(?:/js)?\?for=" + TOKEN), lambda m: {"board": m.group(1)}),
    ("greenhouse", re.compile(r"(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/" + TOKEN), lambda m: {"board": m.group(1)}),
    ("lever", re.compile(r"jobs\.(eu\.)?lever\.co/" + TOKEN), lambda m: {"company": m.group(2), "eu": bool(m.group(1))}),
    ("ashby", re.compile(r"(?:jobs\.ashbyhq\.com|api\.ashbyhq\.com/posting-api/job-board)/" + TOKEN), lambda m: {"board": m.group(1)}),
    ("smartrecruiters", re.compile(r"(?:jobs|careers)\.smartrecruiters\.com/" + TOKEN), lambda m: {"company": m.group(1)}),
    ("smartrecruiters", re.compile(r"api\.smartrecruiters\.com/v1/companies/" + TOKEN), lambda m: {"company": m.group(1)}),
    ("workable", re.compile(r"apply\.workable\.com/(?:api/v\d/accounts/)?" + TOKEN), lambda m: {"account": m.group(1)}),
    ("pinpoint", re.compile(r"([\w-]+)\.pinpointhq\.com"), lambda m: {"subdomain": m.group(1)}),
    (
        "workday",
        re.compile(r"([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:wday/cxs/[\w-]+/)?(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)"),
        lambda m: {"host": f"{m.group(1)}.{m.group(2)}.myworkdayjobs.com", "tenant": m.group(1), "site": m.group(3)},
    ),
    (
        "oracle_hcm",
        re.compile(r"([\w-]+\.fa\.[\w-]+\.oraclecloud\.com)/hcmUI/CandidateExperience/[a-z]{2}/sites/([\w-]+)"),
        lambda m: {"host": m.group(1), "site": m.group(2)},
    ),
    ("icims", re.compile(r"([\w-]+)\.icims\.com"), lambda m: {"subdomain": m.group(1)}),
    ("teamtailor", re.compile(r"([\w-]+)\.teamtailor\.com"), lambda m: {"subdomain": m.group(1)}),
    ("recruitee", re.compile(r"([\w-]+)\.recruitee\.com"), lambda m: {"subdomain": m.group(1)}),
    ("personio", re.compile(r"([\w-]+)\.jobs\.personio\.(?:de|com)"), lambda m: {"subdomain": m.group(1)}),
    ("eightfold", re.compile(r"([\w.-]+)/api/(?:apply/v2|pcsx)/"), lambda m: {"host": m.group(1)}),
    ("eightfold", re.compile(r"eightfold\.ai|eightfold-cdn|pcsx-cdn", re.I), lambda m: {}),
    ("phenom", re.compile(r"phenompeople|cdn\.phenom|phApp\.ddo", re.I), lambda m: {}),
    ("successfactors", re.compile(r"jobs2web|rmkcdn\.successfactors|career\d*\.successfactors", re.I), lambda m: {}),
    ("avature", re.compile(r"avature\.net|avaturecdn", re.I), lambda m: {}),
    ("zoho_recruit", re.compile(r"zohorecruit\.(?:com|in)/([\w-]+)?", re.I), lambda m: {}),
    ("darwinbox", re.compile(r"([\w-]+)\.darwinbox\.in", re.I), lambda m: {"subdomain": m.group(1)}),
]  # fmt: skip

LINK_HINTS = re.compile(r"job|opening|position|vacanc|search|opportunit|role", re.I)


@dataclass
class Candidate:
    source_type: str
    source_config: dict[str, Any]
    found_on: str
    verified_jobs: int | None = None  # None = not verifiable by a simple API call
    error: str | None = None


@dataclass
class Detection:
    slug: str
    name: str
    careers_url: str
    final_url: str | None = None
    page_status: int | None = None
    candidates: list[Candidate] = field(default_factory=list)
    best: Candidate | None = None
    error: str | None = None


def scan_text(text: str, found_on: str) -> list[Candidate]:
    out: list[Candidate] = []
    seen: set[str] = set()
    for source_type, pattern, make_cfg in SIGNATURES:
        for m in pattern.finditer(text):
            cfg = make_cfg(m)
            token = next(iter(cfg.values()), None) if cfg else None
            if isinstance(token, str) and token.lower() in BAD_TOKENS:
                continue
            key = source_type + json.dumps(cfg, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            out.append(Candidate(source_type, cfg, found_on))
    return out


def candidate_links(base_url: str, html: str, limit: int = 3) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        text = (a.get_text() or "") + " " + href
        if LINK_HINTS.search(text):
            full = urljoin(base_url, href).split("#")[0]
            if full not in links and full.rstrip("/") != base_url.rstrip("/"):
                links.append(full)
    # prefer links that look like job search pages
    links.sort(key=lambda u: (0 if re.search(r"search|jobs|openings", u, re.I) else 1, len(u)))
    return links[:limit]


# --- verification against the live API -----------------------------------------------------------


def verify(c: Candidate, client: PoliteClient) -> None:
    """Fill c.verified_jobs (count) for sources that have a simple public listing API."""
    cfg = c.source_config
    try:
        if c.source_type == "greenhouse":
            data = client.get_json(f"https://boards-api.greenhouse.io/v1/boards/{cfg['board']}/jobs")
            c.verified_jobs = len(data.get("jobs", []))
        elif c.source_type == "lever":
            host = "api.eu.lever.co" if cfg.get("eu") else "api.lever.co"
            data = client.get_json(f"https://{host}/v0/postings/{cfg['company']}?mode=json")
            c.verified_jobs = len(data)
        elif c.source_type == "ashby":
            data = client.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{cfg['board']}")
            c.verified_jobs = len(data.get("jobs", []))
        elif c.source_type == "smartrecruiters":
            data = client.get_json(f"https://api.smartrecruiters.com/v1/companies/{cfg['company']}/postings?limit=1")
            c.verified_jobs = int(data.get("totalFound", 0))
        elif c.source_type == "workable":
            data = client.post_json(f"https://apply.workable.com/api/v3/accounts/{cfg['account']}/jobs", json={})
            c.verified_jobs = int(data.get("total", len(data.get("results", []))))
        elif c.source_type == "pinpoint":
            data = client.get_json(f"https://{cfg['subdomain']}.pinpointhq.com/postings.json")
            c.verified_jobs = len(data.get("data", []))
        elif c.source_type == "workday":
            url = f"https://{cfg['host']}/wday/cxs/{cfg['tenant']}/{cfg['site']}/jobs"
            data = client.post_json(url, json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""})
            c.verified_jobs = int(data.get("total", 0))
    except (FetchError, RobotsDisallowed, ValueError, KeyError) as e:
        c.error = str(e)[:300]
        c.verified_jobs = 0 if c.verified_jobs is None else c.verified_jobs


def name_guesses(slug: str, name: str) -> list[str]:
    base = re.sub(r"\(.*?\)", "", name).strip()
    words = re.findall(r"[a-z0-9]+", base.lower())
    guesses = ["".join(words), slug.split("-")[0], "-".join(words)]
    if len(words) > 1:
        guesses.append(words[0] + words[1])
    out: list[str] = []
    for g in guesses:
        if g and g not in out and len(g) > 1:
            out.append(g)
    return out[:3]


def probe_by_name(slug: str, name: str, client: PoliteClient) -> list[Candidate]:
    found: list[Candidate] = []
    for g in name_guesses(slug, name):
        for c in (
            Candidate("greenhouse", {"board": g}, "name-guess"),
            Candidate("lever", {"company": g, "eu": False}, "name-guess"),
            Candidate("ashby", {"board": g}, "name-guess"),
            Candidate("smartrecruiters", {"company": g}, "name-guess"),
        ):
            verify(c, client)
            if c.verified_jobs:
                found.append(c)
        if found:
            break
    return found


# --- main ----------------------------------------------------------------------------------------

PRIORITY = {  # when several candidates exist, prefer a verified simple API, then richer platforms
    "greenhouse": 1, "lever": 1, "ashby": 1, "smartrecruiters": 2, "workable": 2, "pinpoint": 2, "workday": 2,
    "oracle_hcm": 3, "eightfold": 3, "phenom": 4, "successfactors": 4, "icims": 4, "avature": 5,
}  # fmt: skip


def choose_best(cands: list[Candidate]) -> Candidate | None:
    if not cands:
        return None
    verified = [c for c in cands if c.verified_jobs]
    pool = verified or [c for c in cands if c.verified_jobs is None]  # unverifiable platform fingerprints
    if not pool:
        return None
    return sorted(pool, key=lambda c: (PRIORITY.get(c.source_type, 9), -(c.verified_jobs or 0)))[0]


def detect_company(slug: str, name: str, careers_url: str, client: PoliteClient) -> Detection:
    d = Detection(slug=slug, name=name, careers_url=careers_url)
    pages: list[tuple[str, str]] = []
    try:
        r = client.get(careers_url, headers={"Accept": "text/html,application/xhtml+xml"})
        d.final_url, d.page_status = str(r.url), r.status_code
        pages.append((str(r.url), str(r.url) + "\n" + r.text))
        d.candidates.extend(scan_text(pages[0][1], "careers page"))
        if not d.candidates:
            for link in candidate_links(str(r.url), r.text):
                try:
                    r2 = client.get(link, headers={"Accept": "text/html,application/xhtml+xml"})
                except (FetchError, RobotsDisallowed):
                    continue
                d.candidates.extend(scan_text(str(r2.url) + "\n" + r2.text, f"linked page {r2.url}"))
                if d.candidates:
                    break
    except (FetchError, RobotsDisallowed) as e:
        d.error = str(e)[:300]

    for c in d.candidates:
        verify(c, client)
    if not any(c.verified_jobs for c in d.candidates):
        d.candidates.extend(probe_by_name(slug, name, client))
    d.best = choose_best(d.candidates)
    return d


def detect_all(companies: list[tuple[str, str, str]], workers: int = 8) -> list[Detection]:
    with PoliteClient(min_interval=1.2, timeout=25, max_retries=1) as client:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(lambda c: detect_company(c[0], c[1], c[2], client), companies))


def write_report(results: list[Detection]) -> None:
    path = CONFIG_DIR / "detect_report.json"
    path.write_text(json.dumps([asdict(r) for r in results], indent=2, default=str), encoding="utf-8")
