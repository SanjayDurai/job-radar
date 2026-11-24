"""Generic adapters for career sites without a usable JSON API.

  html_links       static HTML listing page(s); job links matched by a regex
  sitemap          the site's sitemap.xml (for sites whose robots.txt blocks search pages but
                   publishes job URLs for crawlers, e.g. Radancy/TalentBrew sites)
  playwright       listing rendered in headless Chromium (JS-only sites), job links by regex

All three read details from the job page: schema.org JobPosting JSON-LD when present
(title, location, description, date, salary), otherwise the page's main readable text.

Common cfg keys:
  url:          listing URL; may contain {term} (URL-encoded search term) and {page}
  link_regex:   regex an absolute job URL must match (group 1, if any, is used as the job id)
  use_terms:    true => run once per search term (needs {term} in url)
  pages:        how many {page} values to try (default 1); page_start (default 1), page_step (default 1)
  title_from:   "text" (anchor text, default) | "slug" (last path part of the URL)
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote, unquote, urljoin, urlsplit

from bs4 import BeautifulSoup

from radar.adapters.base import Adapter, FetchContext, JobPosting, html_to_text, parse_datetime

# --- detail pages ------------------------------------------------------------------------------------


def _jsonld_jobposting(html: str) -> dict[str, Any] | None:
    for block in re.findall(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", html, re.S | re.I):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                if item.get("@type") == "JobPosting" or (isinstance(item.get("@type"), list) and "JobPosting" in item["@type"]):
                    return item
                stack.extend(v for v in item.values() if isinstance(v, dict | list))
            elif isinstance(item, list):
                stack.extend(item)
    return None


def _jsonld_location(job: dict[str, Any]) -> tuple[str | None, list[str], bool]:
    locs = job.get("jobLocation") or []
    locs = locs if isinstance(locs, list) else [locs]
    out = []
    for loc in locs:
        addr = (loc or {}).get("address") or {}
        if isinstance(addr, str):
            out.append(addr)
            continue
        country = addr.get("addressCountry")
        country = country.get("name") if isinstance(country, dict) else country
        parts = [addr.get("addressLocality"), addr.get("addressRegion"), country]
        text = ", ".join(str(p) for p in parts if p)
        if text:
            out.append(text)
    remote = str(job.get("jobLocationType", "")).upper() == "TELECOMMUTE"
    if remote and not out:
        req = job.get("applicantLocationRequirements") or []
        req = req if isinstance(req, list) else [req]
        out = [f"Remote - {r.get('name')}" for r in req if isinstance(r, dict) and r.get("name")] or ["Remote"]
    return (out[0] if out else None), out[1:], remote


def _main_text(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "svg", "form", "iframe"]):
        tag.decompose()
    node = soup.find("main") or soup.find("article") or soup.find(attrs={"role": "main"}) or soup.body or soup
    text = html_to_text(str(node))
    return text[:20000] if text else None


def enrich_from_detail_page(job: JobPosting, html: str) -> str | None:
    """Fill location/date/salary from JSON-LD when available; return the description text."""
    ld = _jsonld_jobposting(html)
    if not ld:
        return _main_text(html)
    loc, others, remote = _jsonld_location(ld)
    if loc and not job.location:
        job.location, job.locations = loc, others
    job.is_remote = job.is_remote or remote
    job.posted_at = job.posted_at or parse_datetime(ld.get("datePosted"))
    if ld.get("title") and (not job.title or job.title.islower()):
        job.title = html_to_text(ld["title"]) or job.title
    sal = ld.get("baseSalary") or {}
    if isinstance(sal, dict) and isinstance(sal.get("value"), dict):
        v = sal["value"]
        job.salary_min = job.salary_min or _num(v.get("minValue") or v.get("value"))
        job.salary_max = job.salary_max or _num(v.get("maxValue"))
        job.salary_currency = job.salary_currency or sal.get("currency")
        unit = str(v.get("unitText", "")).lower()
        job.salary_period = job.salary_period or {"year": "year", "month": "month", "hour": "hour"}.get(unit)
    return html_to_text(ld.get("description")) or _main_text(html)


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --- listing helpers ----------------------------------------------------------------------------------


def _title_from_slug(url: str) -> str:
    path = [p for p in urlsplit(url).path.split("/") if p]
    slug = next((p for p in reversed(path) if re.search(r"[a-z]{3}", p, re.I) and not p.isdigit()), path[-1] if path else "")
    slug = re.sub(r"^\d+[-_]", "", unquote(slug))
    slug = re.sub(r"[-_]jid[-_]?\d+$", "", slug)
    return re.sub(r"[-_]+", " ", slug).strip().title()


GENERIC_ANCHOR = re.compile(
    r"^(see (full )?(role|job)( description)?|learn more|read more|view( job| details| role)?|apply( now)?|details|more|"
    r"show more jobs?|save( job)?)$",
    re.I,
)
TRAILING_TYPE = re.compile(r"\s+(full[- ]time|part[- ]time|contract|internship|temporary|permanent)\s*$", re.I)


def _clean_anchor_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = TRAILING_TYPE.sub("", text)
    return "" if GENERIC_ANCHOR.match(text) else text[:200]


def listing_urls(cfg: dict[str, Any], ctx: FetchContext) -> list[str]:
    terms = (cfg.get("search_terms") or ctx.search_terms) if cfg.get("use_terms") else [""]
    pages = int(cfg.get("pages", 1))
    start, step = int(cfg.get("page_start", 1)), int(cfg.get("page_step", 1))
    urls = []
    for term in terms:
        for i in range(pages):
            urls.append(cfg["url"].replace("{term}", quote(term)).replace("{page}", str(start + i * step)))
    return list(dict.fromkeys(urls))


def extract_job_links(html: str, base_url: str, cfg: dict[str, Any]) -> list[JobPosting]:
    pattern = re.compile(cfg["link_regex"])
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, JobPosting] = {}
    # Some sites group jobs under a heading per location (e.g. SmartRecruiters "Bengaluru, India")
    section_loc: dict[int, str] = {}
    if cfg.get("section_selector"):
        for section in soup.select(cfg["section_selector"]):
            heading = section.select_one(cfg.get("section_title_selector", "h3"))
            if heading:
                for link in section.find_all("a", href=True):
                    section_loc[id(link)] = heading.get_text(" ", strip=True)
    for a in soup.find_all("a", href=True):
        url = urljoin(base_url, a["href"]).split("#")[0]
        m = pattern.search(url)
        if not m:
            continue
        job_id = m.group(1) if m.groups() else url
        # Cards often put "Title / Team / Location" on separate lines inside the link: title = first line
        lines = [ln.strip() for ln in a.get_text("\n").split("\n") if ln.strip()]
        text = _clean_anchor_text(lines[0] if lines else "")
        loc_line = cfg.get("location_line")
        location = lines[int(loc_line)] if loc_line is not None and int(loc_line) < len(lines) else None
        location = location or section_loc.get(id(a))
        use_slug = cfg.get("title_from") == "slug" or len(text) < 4
        title = _title_from_slug(url) if use_slug else text
        if job_id in found:
            prev = found[job_id]
            # prefer real anchor text over a slug-derived title, then the longer text
            if not use_slug and (prev.description == "slug" or len(title) > len(prev.title)):
                prev.title, prev.description = title, None
            continue
        if use_slug:
            found[job_id] = JobPosting(external_id=str(job_id), title=title, url=url, location=location, description="slug")
            continue
        found[job_id] = JobPosting(external_id=str(job_id), title=title, url=url, location=location)
    for job in found.values():
        if job.description == "slug":  # internal marker: title came from the URL slug
            job.description = None
    return list(found.values())


class _DetailFromPage(Adapter):
    needs_description_fetch = True

    def fetch_description(self, job: JobPosting, cfg: dict[str, Any], ctx: FetchContext) -> str | None:
        r = ctx.client.get(job.url, headers={"Accept": "text/html,application/xhtml+xml"})
        if r.status_code >= 400:
            return None
        return enrich_from_detail_page(job, r.text)


class HtmlLinks(_DetailFromPage):
    source_type = "html_links"

    def list_jobs(self, cfg: dict[str, Any], ctx: FetchContext) -> list[JobPosting]:
        jobs: dict[str, JobPosting] = {}
        for url in listing_urls(cfg, ctx):
            r = ctx.client.get(url, headers={"Accept": "text/html,application/xhtml+xml"})
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code} from {url}")
            page_jobs = extract_job_links(r.text, str(r.url), cfg)
            new = [j for j in page_jobs if j.external_id not in jobs]
            for j in new:
                jobs[j.external_id] = j
            if "{page}" in cfg["url"] and not new:
                break  # ran past the last page
        return list(jobs.values())


class Sitemap(_DetailFromPage):
    """cfg: {url: sitemap.xml, link_regex, max_sub_sitemaps?: 20}. Titles come from URL slugs."""

    source_type = "sitemap"

    def list_jobs(self, cfg: dict[str, Any], ctx: FetchContext) -> list[JobPosting]:
        pattern = re.compile(cfg["link_regex"])
        todo, seen_maps, jobs = [cfg["url"]], set(), {}
        while todo and len(seen_maps) < int(cfg.get("max_sub_sitemaps", 20)):
            sm = todo.pop(0)
            if sm in seen_maps:
                continue
            seen_maps.add(sm)
            xml = ctx.client.get(sm).text
            for loc, lastmod in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>(?:\s*<lastmod>([^<]+)</lastmod>)?", xml):
                loc = loc.replace("&amp;", "&")
                if "<sitemapindex" in xml[:500]:
                    todo.append(loc)
                    continue
                m = pattern.search(loc)
                if m:
                    jid = m.group(1) if m.groups() else loc
                    job = JobPosting(external_id=str(jid), title=_title_from_slug(loc), url=loc,
                                     posted_at=parse_datetime(lastmod) if lastmod else None)  # fmt: skip
                    if cfg.get("location_segment") is not None:  # e.g. /job/<city>/<title>/... on TalentBrew
                        segs = [s for s in urlsplit(loc).path.split("/") if s]
                        idx = int(cfg["location_segment"])
                        if idx < len(segs):
                            job.location = unquote(segs[idx]).replace("-", " ").title()
                    jobs[jid] = job
        return list(jobs.values())


class PlaywrightLinks(_DetailFromPage):
    """Rendered listing pages. cfg adds: wait_for (CSS selector), scrolls (int), detail_with_browser (bool)."""

    source_type = "playwright"

    def list_jobs(self, cfg: dict[str, Any], ctx: FetchContext) -> list[JobPosting]:
        from playwright.sync_api import sync_playwright

        jobs: dict[str, JobPosting] = {}
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_context(user_agent=ctx.client.user_agent).new_page()
                for url in listing_urls(cfg, ctx):
                    if not ctx.client.allowed(url):
                        raise RuntimeError(f"robots.txt disallows {url}")
                    ctx.client.wait_turn(url)
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    try:
                        if cfg.get("wait_for"):
                            page.wait_for_selector(cfg["wait_for"], timeout=20000)
                        else:
                            page.wait_for_load_state("networkidle", timeout=20000)
                    except Exception:
                        pass  # take whatever rendered
                    for _ in range(int(cfg.get("scrolls", 0))):
                        page.mouse.wheel(0, 5000)
                        page.wait_for_timeout(1200)
                    new = [j for j in extract_job_links(page.content(), page.url, cfg) if j.external_id not in jobs]
                    for j in new:
                        jobs[j.external_id] = j
                    if "{page}" in cfg["url"] and not new:
                        break
            finally:
                browser.close()
        return list(jobs.values())
