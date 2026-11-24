"""Regenerates the adapter fixtures in this folder. Shapes mirror the live APIs (trimmed, made-up data).

Run:  uv run python tests/fixtures/make_fixtures.py
"""

import json
from pathlib import Path

HERE = Path(__file__).parent

JSON_FIXTURES = {
    "greenhouse.json": {"jobs": [{
        "id": 4011, "title": "Machine Learning Engineer ", "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/4011",
        "location": {"name": "Chennai, India"}, "offices": [{"name": "Chennai", "location": "Chennai, Tamil Nadu, India"}],
        "departments": [{"name": "AI Platform"}], "first_published": "2026-11-20T10:00:00-05:00",
        "content": "&lt;p&gt;Build LLM features.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;2+ years Python&lt;/li&gt;&lt;/ul&gt;"}]},
    "lever.json": [{
        "id": "a1b2", "text": "AI Engineer", "hostedUrl": "https://jobs.lever.co/acme/a1b2", "createdAt": 1795400000000,
        "categories": {"location": "Bangalore, Karnataka", "team": "Data", "commitment": "Full-time",
                       "allLocations": ["Bangalore, Karnataka", "Remote - India"]},
        "country": "IN", "workplaceType": "hybrid", "descriptionPlain": "We are building agents.",
        "lists": [{"text": "Requirements", "content": "<li>1-3 years experience</li>"}],
        "additionalPlain": "Visa sponsorship available.",
        "salaryRange": {"min": 2000000, "max": 3000000, "currency": "INR", "interval": "per-year-salary"}}],
    "ashby.json": {"apiVersion": "1", "jobs": [
        {"id": "u-1", "title": "Applied AI Engineer", "jobUrl": "https://jobs.ashbyhq.com/acme/u-1", "location": "Toronto",
         "secondaryLocations": [{"location": "Remote - Canada"}], "department": "Engineering", "isRemote": False,
         "workplaceType": "Hybrid", "employmentType": "FullTime", "publishedAt": "2026-11-18T12:00:00.000+00:00", "isListed": True,
         "descriptionPlain": "Ship GenAI products.", "address": {"postalAddress": {"addressCountry": "Canada"}},
         "compensation": {"summaryComponents": [{"compensationType": "Salary", "minValue": 120000, "maxValue": 150000,
                                                 "currencyCode": "CAD", "interval": "1 YEAR"}]}},
        {"id": "u-2", "title": "Hidden", "jobUrl": "x", "isListed": False}]},
    "workable_list.json": {"total": 1, "nextPage": None, "results": [{
        "shortcode": "ABC123", "title": "ML Engineer - Open Source", "remote": True, "workplace": "remote",
        "location": {"country": "France", "city": "Paris"}, "locations": [{"country": "France", "city": "Paris"}],
        "department": ["Engineering"], "type": "full", "published": "2026-11-10T00:00:00.000Z"}]},
    "workable_detail.json": {"description": "<p>Work on transformers.</p>", "requirements": "<ul><li>Python</li></ul>",
                             "benefits": "<p>Remote</p>"},
    "pinpoint.json": {"data": [{
        "id": 77, "title": "Data Scientist", "url": "https://tabby.pinpointhq.com/postings/77",
        "location": {"name": "Dubai", "city": "Dubai"}, "workplace_type": "onsite", "employment_type_text": "Full Time",
        "description": "<p>Credit risk models.</p>", "compensation_minimum": "25000", "compensation_maximum": "35000",
        "compensation_currency": "AED", "compensation_frequency": "month"}]},
    "workday_list.json": {"total": 2, "jobPostings": [
        {"title": "Software Engineer II - AI", "externalPath": "/job/Bengaluru/Software-Engineer-II---AI_R-123",
         "locationsText": "Bengaluru, India", "postedOn": "Posted 3 Days Ago"},
        {"title": "Data Scientist", "externalPath": "/job/Chennai/Data-Scientist_R-456", "locationsText": "2 Locations",
         "postedOn": "Posted Today"}]},
    "workday_detail.json": {"jobPostingInfo": {
        "jobDescription": "<p>Build ML pipelines. 2-4 years of experience.</p>", "location": "Bengaluru, India",
        "additionalLocations": ["Chennai, India"], "timeType": "Full time", "startDate": "2026-11-20",
        "externalUrl": "https://acme.wd5.myworkdayjobs.com/External/job/Bengaluru/Software-Engineer-II---AI_R-123",
        "country": {"descriptor": "India"}}},
    "oracle_list.json": {"items": [{"TotalJobsCount": 1, "requisitionList": [{
        "Id": "300123", "Title": "Machine Learning Engineer", "PostedDate": "2026-11-19",
        "PrimaryLocation": "Mumbai, Maharashtra, India", "PrimaryLocationCountry": "IN", "ShortDescriptionStr": "ML for payments",
        "secondaryLocations": [{"Name": "Bengaluru, Karnataka, India"}]}]}]},
    "oracle_detail.json": {"items": [{"ExternalDescriptionStr": "<p>Design models.</p>",
                                      "ExternalQualificationsStr": "<p>3+ years Python.</p>"}]},
    "eightfold_search.json": {"status": 200, "data": {"count": 1, "positions": [{
        "id": 1970393557050202, "name": "Software Engineer - AI",
        "locations": ["India, Karnataka, Bangalore", "India, Telangana, Hyderabad"], "postedTs": 1793644200,
        "department": "CoreAI", "workLocationOption": "onsite", "positionUrl": "/careers/job/1970393557050202"}]}},
    "eightfold_detail.json": {"data": {"jobDescription": "<b>Overview</b><p>Agents at scale.</p>",
                                       "publicUrl": "https://jobs.example.com/careers/job/1970393557050202"}},
    "amazon.json": {"hits": 1, "jobs": [{
        "id_icims": "3123456", "title": "Applied Scientist I, Alexa AI", "job_path": "/en/jobs/3123456/applied-scientist-i-alexa-ai",
        "normalized_location": "Chennai, Tamil Nadu, IND", "country_code": "IND", "job_category": "Machine Learning Science",
        "posted_date": "November 20, 2026", "description": "Work on LLMs.<br/>",
        "basic_qualifications": "- Experience with Python", "preferred_qualifications": "- PhD"}]},
    "atlassian.json": [{
        "id": 27339, "title": "Machine Learning Engineer", "locations": ["Bengaluru - India -   Bengaluru", "Remote - India"],
        "category": "Engineering", "overview": "<p>Rovo AI agents.</p>", "responsibilities": "<ul><li>Ship models</li></ul>",
        "qualifications": "<p>2+ years</p>",
        "portalJobPost": {"portalUrl": "https://careers-apac-atlassian.icims.com/jobs/27339/job", "updatedDate": "2026-11-09 12:21 PM"}}],
    "phonepe.json": {"totalCount": 3, "results": [
        {"status": "PUBLIC", "applyUrl": None, "type": "Full-time", "title": "Software Engineer - ML", "department": "Engineering",
         "location": "Bengaluru", "updatedAt": "/Date(1795400000000)/"},
        {"status": "NOT_PUBLISHED", "title": "Hidden", "location": "Pune"},
        {"status": "PRIVATE", "title": "Private", "location": "Pune"}]},
    "mercari.json": {"data": {"jobs": {"nodes": [{"id": "cG9zdDox", "slug": "368ce2af88",
                                                  "title": "Machine Learning Engineer – Mercari",
                                                  "locations": {"nodes": [{"slug": "roppongi"}]}}]}}},
    "jibe.json": {"totalCount": 1, "jobs": [{"data": {
        "req_id": "R-77", "slug": "77", "title": "Machine Learning Scientist II", "full_location": "Amsterdam, Netherlands",
        "country": "Netherlands", "employment_type": "FULL_TIME", "posted_date": "2026-11-15T00:00:00+0000",
        "description": "<p>Ranking models.</p>"}}]},
    "emirates.json": {"status": "ok", "data": [{
        "system": "Avature", "title": "Data Scientist", "reqid": "267", "city": "Dubai", "state": "Dubai",
        "country": "United Arab Emirates", "postingdate": 1748390400000, "category": "IT",
        "jobdescription": "<h5>Job Purpose</h5><p>Forecasting.</p>"}]},
}  # fmt: skip

TEXT_FIXTURES = {
    "html_listing.html": """<html><body><ul>
<li><a href="/acme/job/okYWAfwy"><div>Data Scientist</div><div>Analytics</div><div>Chennai</div></a>
    <a href="/acme/job/okYWAfwy">See full role description</a></li>
<li><a href="/acme/job/ofnQAfwM">Sales Lead Full-time</a></li>
<li><a href="/about">About us</a></li>
</ul></body></html>""",
    "html_detail.html": """<html><head><script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting",
"title":"Data Scientist","datePosted":"2026-10-09","description":"&lt;p&gt;Build NLP models. 1-3 years.&lt;/p&gt;",
"jobLocation":[{"@type":"Place","address":{"@type":"PostalAddress","addressLocality":"Chennai","addressCountry":"India"}}],
"baseSalary":{"@type":"MonetaryAmount","currency":"INR","value":{"@type":"QuantitativeValue","minValue":1800000,
"maxValue":2400000,"unitText":"YEAR"}}}</script></head><body><main><h1>Data Scientist</h1></main></body></html>""",
    "sitemap.xml": """<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://jobs.acme.com/job/bengaluru/machine-learning-engineer/27595/89012345</loc><lastmod>2026-11-20</lastmod></url>
<url><loc>https://jobs.acme.com/job/mountain-view/product-marketing-manager/27595/89012346</loc></url>
<url><loc>https://jobs.acme.com/category/software-engineering-jobs/27595/68357/1</loc></url>
</urlset>""",
    "google.html": (
        '<html><script>AF_initDataCallback({data:[[["104937753002549958","Software Engineer, AI/ML, Early Career",'
        '"https://www.google.com/about/careers/applications/signin?jobId\\u003dX",'
        '[null,"\\u003cul\\u003e\\n\\u003cli\\u003eBuild Gemini features.\\u003c/li\\u003e\\u003c/ul\\u003e"],'
        '[null,"\\u003cp\\u003e1 year of experience.\\u003c/p\\u003e"],[["Bengaluru, Karnataka, India",["x"],"Bengaluru"]]],'
        '["129129141264884422","Senior Staff Engineer","https://www.google.com/about/careers/applications/signin?jobId\\u003dY",'
        '[null,"\\u003cp\\u003eLead.\\u003c/p\\u003e"],[["Hyderabad, Telangana, India"]]]]]});</script></html>'
    ),
}

if __name__ == "__main__":
    for name, data in JSON_FIXTURES.items():
        (HERE / name).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    for name, text in TEXT_FIXTURES.items():
        (HERE / name).write_text(text, encoding="utf-8")
    print(f"wrote {len(JSON_FIXTURES) + len(TEXT_FIXTURES)} fixtures")
