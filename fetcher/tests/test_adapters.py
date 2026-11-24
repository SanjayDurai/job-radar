"""Fixture-based tests: each adapter parses a saved response (no network)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from radar.adapters import FetchContext, get_adapter
from radar.adapters.generic import extract_job_links
from radar.adapters.workday import parse_posted_on
from radar.http import PoliteClient

FIX = Path(__file__).parent / "fixtures"


def fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def make_ctx(routes: dict[str, str], terms: list[str] | None = None) -> FetchContext:
    """routes: URL substring -> fixture file. First match wins; robots.txt is always 404 (allowed)."""

    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if url.endswith("/robots.txt"):
            return httpx.Response(404)
        for needle, fixture in routes.items():
            if needle in url:
                body = fx(fixture)
                ctype = "application/json" if fixture.endswith(".json") else "text/html"
                return httpx.Response(200, text=body, headers={"content-type": ctype})
        return httpx.Response(404, text="not found")

    client = PoliteClient(min_interval=0, transport=httpx.MockTransport(handler))
    return FetchContext(client=client, search_terms=terms or ["machine learning"])


def run(source_type: str, cfg: dict, routes: dict[str, str], terms=None):
    ctx = make_ctx(routes, terms)
    adapter = get_adapter(source_type)
    jobs = adapter.list_jobs(cfg, ctx)
    return adapter, ctx, jobs


def test_greenhouse():
    _, _, jobs = run("greenhouse", {"board": "acme"}, {"boards-api.greenhouse.io": "greenhouse.json"})
    (j,) = jobs
    assert (j.external_id, j.title, j.location) == ("4011", "Machine Learning Engineer", "Chennai, India")
    assert "Build LLM features." in j.description and "• 2+ years Python" in j.description
    assert j.department == "AI Platform" and j.posted_at.year == 2026


def test_lever():
    _, _, (j,) = run("lever", {"company": "acme"}, {"api.lever.co": "lever.json"})
    assert j.title == "AI Engineer" and j.location == "Bangalore, Karnataka"
    assert j.locations == ["Remote - India"]
    assert "1-3 years experience" in j.description and "Visa sponsorship" in j.description
    assert (j.salary_min, j.salary_currency, j.salary_period) == (2000000, "INR", "year")


def test_ashby_skips_unlisted_and_reads_salary():
    _, _, jobs = run("ashby", {"board": "acme"}, {"api.ashbyhq.com": "ashby.json"})
    assert [j.title for j in jobs] == ["Applied AI Engineer"]
    j = jobs[0]
    assert j.country == "Canada" and j.locations == ["Remote - Canada"]
    assert (j.salary_min, j.salary_max, j.salary_currency, j.salary_period) == (120000, 150000, "CAD", "year")


def test_workable_list_and_detail():
    adapter, ctx, (j,) = run(
        "workable",
        {"account": "huggingface"},
        {"/api/v3/accounts/": "workable_list.json", "/api/v2/accounts/": "workable_detail.json"},
    )
    assert j.title == "ML Engineer - Open Source" and j.is_remote
    assert j.url == "https://apply.workable.com/huggingface/j/ABC123/"
    desc = adapter.fetch_description(j, {"account": "huggingface"}, ctx)
    assert "transformers" in desc and "Python" in desc


def test_pinpoint():
    _, _, (j,) = run("pinpoint", {"subdomain": "tabby"}, {"pinpointhq.com": "pinpoint.json"})
    assert j.title == "Data Scientist" and j.location == "Dubai"
    assert (j.salary_min, j.salary_currency, j.salary_period) == (25000.0, "AED", "month")


def test_workday_list_dedupes_across_terms_and_reads_detail():
    cfg = {"host": "acme.wd5.myworkdayjobs.com", "tenant": "acme", "site": "External"}
    adapter, ctx, jobs = run(
        "workday",
        cfg,
        {"/jobs": "workday_list.json", "/job/": "workday_detail.json"},
        terms=["machine learning", "python"],
    )
    assert [j.title for j in jobs] == ["Software Engineer II - AI", "Data Scientist"]  # deduped across 2 terms
    assert jobs[1].location is None  # "2 Locations" is left unknown for the detail page to resolve
    j = jobs[0]
    assert j.url == "https://acme.wd5.myworkdayjobs.com/en-US/External/job/Bengaluru/Software-Engineer-II---AI_R-123"
    desc = adapter.fetch_description(j, cfg, ctx)
    assert "2-4 years" in desc
    assert j.locations == ["Bengaluru, India", "Chennai, India"] and j.country == "India"


def test_workday_posted_on():
    from datetime import UTC, datetime

    now = datetime(2026, 11, 23, tzinfo=UTC)
    assert parse_posted_on("Posted Today", now) == now
    assert parse_posted_on("Posted 3 Days Ago", now).day == 20
    assert parse_posted_on("Posted 30+ Days Ago", now).month == 10
    assert parse_posted_on(None) is None


def test_oracle_hcm():
    cfg = {"host": "acme.fa.us2.oraclecloud.com", "site": "CX_1"}
    adapter, ctx, (j,) = run(
        "oracle_hcm",
        cfg,
        {"recruitingCEJobRequisitions?": "oracle_list.json", "recruitingCEJobRequisitionDetails": "oracle_detail.json"},
    )
    assert j.title == "Machine Learning Engineer" and j.location == "Mumbai, Maharashtra, India"
    assert j.locations == ["Bengaluru, Karnataka, India"]
    assert j.url.endswith("/sites/CX_1/job/300123")
    assert "3+ years Python." in adapter.fetch_description(j, cfg, ctx)


def test_eightfold_pcsx():
    cfg = {"host": "jobs.example.com", "domain": "example.com", "location": "India"}
    adapter, ctx, (j,) = run(
        "eightfold", cfg, {"/api/pcsx/search": "eightfold_search.json", "position_details": "eightfold_detail.json"}
    )
    assert j.title == "Software Engineer - AI" and j.location == "India, Karnataka, Bangalore"
    assert j.url == "https://jobs.example.com/careers/job/1970393557050202"
    assert "Agents at scale." in adapter.fetch_description(j, cfg, ctx)


def test_amazon():
    _, _, (j,) = run("amazon", {"country": "IND"}, {"amazon.jobs": "amazon.json"})
    assert j.title == "Applied Scientist I, Alexa AI" and j.country == "IND"
    assert j.url == "https://www.amazon.jobs/en/jobs/3123456/applied-scientist-i-alexa-ai"
    assert "Basic qualifications" in j.description and j.posted_at.day == 20


def test_atlassian():
    _, _, (j,) = run("atlassian", {}, {"atlassian.com/endpoint": "atlassian.json"})
    assert j.location == "Bengaluru - India - Bengaluru" and j.is_remote
    assert "Rovo AI agents." in j.description


def test_google_embedded_results():
    _, _, jobs = run("google", {"location": "India", "pages": 1}, {"google.com/about/careers": "google.html"})
    assert [j.title for j in jobs] == ["Software Engineer, AI/ML, Early Career", "Senior Staff Engineer"]
    j = jobs[0]
    assert j.location == "Bengaluru, Karnataka, India"
    assert "Build Gemini features." in j.description and "1 year of experience." in j.description
    assert j.url.endswith("/104937753002549958-software-engineer-ai-ml-early-career")


def test_phonepe_public_only():
    _, _, jobs = run("phonepe", {}, {"phonepe.com": "phonepe.json"})
    assert [j.title for j in jobs] == ["Software Engineer - ML"]
    assert jobs[0].posted_at is not None and len(jobs[0].external_id) == 16


def test_mercari():
    _, _, (j,) = run("mercari", {}, {"careers.mercari.com/api": "mercari.json"})
    assert j.location == "Roppongi, Japan" and j.url == "https://careers.mercari.com/en/jobs/368ce2af88/"


def test_jibe():
    _, _, (j,) = run("jibe", {"base": "https://jobs.booking.com", "path": "booking"}, {"/api/jobs": "jibe.json"})
    assert j.title == "Machine Learning Scientist II" and j.location == "Amsterdam, Netherlands"
    assert j.url == "https://jobs.booking.com/booking/jobs/77" and "Ranking models." in j.description


def test_emirates():
    _, _, (j,) = run("emirates", {}, {"emiratesgroupcareers.com/api": "emirates.json"})
    assert j.location == "Dubai, Dubai, United Arab Emirates" and "Forecasting." in j.description


def test_html_links_title_first_line_and_generic_anchor_text():
    cfg = {"url": "https://jobs.example.com/acme/jobs", "link_regex": r"/acme/job/(\w+)", "location_line": 2}
    jobs = extract_job_links(fx("html_listing.html"), cfg["url"], cfg)
    assert [(j.external_id, j.title, j.location) for j in jobs] == [
        ("okYWAfwy", "Data Scientist", "Chennai"),
        ("ofnQAfwM", "Sales Lead", None),  # "Full-time" suffix stripped
    ]


def test_html_links_location_from_section_heading():
    html = """<section class="openings-section"><h3 class="opening-title">Bengaluru, India</h3>
      <a href="https://jobs.smartrecruiters.com/Acme/7440001-ml-engineer"><h4>ML Engineer</h4><p>Full-time</p></a></section>
      <section class="openings-section"><h3 class="opening-title">Austin, TX, US</h3>
      <a href="https://jobs.smartrecruiters.com/Acme/7440002-data-scientist"><h4>Data Scientist</h4></a></section>"""
    cfg = {"link_regex": r"jobs\.smartrecruiters\.com/Acme/(\d+)", "section_selector": "section.openings-section",
           "section_title_selector": "h3.opening-title"}  # fmt: skip
    jobs = extract_job_links(html, "https://careers.smartrecruiters.com/Acme", cfg)
    assert [(j.title, j.location) for j in jobs] == [("ML Engineer", "Bengaluru, India"), ("Data Scientist", "Austin, TX, US")]


def test_html_links_detail_from_jsonld():
    cfg = {"url": "https://jobs.example.com/acme/jobs", "link_regex": r"/acme/job/(\w+)"}
    adapter, ctx, jobs = run("html_links", cfg, {"/acme/jobs": "html_listing.html", "/acme/job/": "html_detail.html"})
    j = jobs[0]
    j.location = None
    desc = adapter.fetch_description(j, cfg, ctx)
    assert "Build NLP models." in desc
    assert j.location == "Chennai, India" and j.posted_at.month == 10
    assert (j.salary_min, j.salary_max, j.salary_currency, j.salary_period) == (1800000.0, 2400000.0, "INR", "year")


def test_sitemap_titles_and_city_from_url():
    cfg = {"url": "https://jobs.acme.com/sitemap.xml", "link_regex": r"/job/[^/]+/[^/]+/\d+/(\d+)", "location_segment": 1}
    _, _, jobs = run("sitemap", cfg, {"sitemap.xml": "sitemap.xml"})
    assert [(j.external_id, j.title, j.location) for j in jobs] == [
        ("89012345", "Machine Learning Engineer", "Bengaluru"),
        ("89012346", "Product Marketing Manager", "Mountain View"),
    ]
    assert jobs[0].posted_at is not None


@pytest.mark.parametrize("name", sorted(p.name for p in FIX.glob("*.json")))
def test_fixtures_are_valid_json(name):
    json.loads(fx(name))


def test_clean_text_removes_bytes_postgres_rejects():
    from radar.adapters.base import clean_text

    assert clean_text("ok \x00 text \ud83d end") == "ok  text  end"
    assert clean_text("Tamil Nadu’s AI hub") == "Tamil Nadu’s AI hub"
    assert clean_text(None) is None
