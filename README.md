# Personal Job Radar

Daily check of ~100 target companies' careers pages for new AI/ML roles that fit my profile, scored and shown on a private dashboard. Free-tier only.

> Full README (setup, adding adapters, tuning filters, troubleshooting) comes in Phase 6. Quick local setup:

## Local development (Windows)

```powershell
# one time
pip install --user uv
Copy-Item .env.example .env
.\scripts\localdb.ps1 init          # private Postgres on port 5433 (uses the installed PostgreSQL 18)

# fetcher
cd fetcher
python -m uv sync
python -m uv run radar db-upgrade    # apply migrations
python -m uv run radar import-excel  # sync Job_Switch_Top100_Companies.xlsx -> DB + config/companies.yaml
python -m uv run radar companies     # show the companies table
python -m uv run pytest              # tests (set TEST_DATABASE_URL=postgresql://radar@localhost:5433/radar_test for DB tests)
```

Editing the Excel (adding/removing companies) and re-running `radar import-excel` is safe: job history is kept and removed companies are only marked inactive.

## Adding or fixing a company

Every company's fetch settings live in [`config/companies.yaml`](config/companies.yaml) (reviewable in git).

1. `python -m uv run radar detect --only <slug>` — scans the careers page for a known ATS and verifies it live.
   Verified matches are written to the YAML; *name-guess* matches are only printed (they can be a different company).
2. Or edit the entry by hand. Common source types:

   | source_type | source_config |
   |---|---|
   | `greenhouse` | `{board: <token>}` (from `boards.greenhouse.io/<token>`) |
   | `lever` | `{company: <slug>}` |
   | `ashby` | `{board: <name>}` |
   | `workday` | `{host: x.wd5.myworkdayjobs.com, tenant: x, site: <site>}` (from the careers URL) |
   | `eightfold` | `{host, domain, location: India}` |
   | `oracle_hcm` | `{host: xxx.fa.<dc>.oraclecloud.com, site: CX_1}` |
   | `html_links` | `{url, link_regex}` (+ optional `use_terms` with `{term}` in url, `pages` with `{page}`) |
   | `sitemap` | `{url: .../sitemap.xml, link_regex}` |
   | `playwright` | like `html_links`, for pages that need a browser |
   | `manual` | `{}` — shown in the dashboard's "check manually" list; put the reason in `notes` |
3. `python -m uv run radar try <slug> --describe` — runs just that adapter live and prints sample jobs.
4. `python -m uv run radar import-excel` (or any `radar run`) copies the YAML into the database.

`python -m uv run radar coverage` shows every company's source, health and last error.

## Layout

| Path | What |
|---|---|
| `config/profile.yaml` | my experience start date, skills, title keywords, exclusions, pay floors |
| `config/scoring.yaml` | score weights, FX table, LLM settings |
| `config/companies.yaml` | how each company is fetched (ATS type + token); reviewable in git |
| `fetcher/` | Python 3.12: import, adapters, scoring, CLI (`radar`) |
| `fetcher/migrations/` | Alembic schema migrations |
| `web/` | Next.js dashboard (Phase 4) |
