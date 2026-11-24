# Build & deploy: Personal Job Radar

You are building a small, personal, single-user system for me. Read this whole file, then **show me a short plan (architecture, ATS coverage approach, what accounts/keys you'll need from me) and wait for my OK before writing code.** After that, build in the phases below, verifying each phase works before moving on.

---

## 1. Goal

Every day, automatically check the careers pages of the ~100 companies in `Job_Switch_Top100_Companies.xlsx` (sheet **"Companies"**, in this folder) for **new openings that match my profile**, score how well each fits me, and show them on a clean dashboard I open each morning. One user (me). Low cost (free tiers wherever possible). Low maintenance.

## 2. About me (use this for filtering and scoring)

- **Current role:** Systems Engineer at TCS Chennai, working as an AI automation engineer on a Toyota Motors North America project. First company.
- **Experience:** ~1.3 years as of Nov 2026. Calculate my experience dynamically from a config value (`career_start: 2025-08`) so it stays correct over time.
- **Skills:** Python, GenAI / LLMs, AI/ML, agentic AI, SQL, AWS Lambda, automation.
- **Target roles (title keywords):** AI Engineer, ML Engineer, Machine Learning, GenAI / Generative AI, LLM, Agentic / AI Agents, Applied Scientist, Applied AI, Software Engineer (AI/ML), Data Scientist, MLOps, AI Automation, Python Engineer.
- **Experience fit:** roles asking 0–3 years (allow up to "3+" / "2-4"). Levels like SDE I, SDE II, Engineer I/II, Associate, L3/L4, MTS 1/2, Software Engineer (non-senior).
- **Exclude:** Senior, Staff, Principal, Lead, Manager, Director, Head, Architect, VP, Intern, Apprentice, roles requiring 5+ years, non-engineering roles (sales, marketing, legal, HR, finance, ops). Also skip roles restricted to citizens/nationals (e.g. "UAE Nationals", "US citizens only", "Emiratisation").
- **Location rules & minimum pay** (per the "Region" column in the sheet):
  - **Chennai** (or remote while living in India): minimum ₹15 LPA
  - **Other Indian city:** minimum ₹20 LPA
  - **Abroad:** minimum ₹30 LPA equivalent. The job must be in the company's country listed in the sheet. Strong boost if the posting mentions visa sponsorship or relocation; penalty if it says "must have existing right to work".
  - **Remote:** must allow working from India.
  - Most postings don't show salary. If salary *is* shown and is below my minimum (convert currencies with a static, configurable rate table), drop the score heavily but keep the job visible under a "below pay bar" flag.
- **Preference order:** Priority column (P1 Dream > P2 Strong > P3 Good) gives a small score boost.

## 3. Data source: the Excel sheet

- Seed a `companies` table from the **Companies** sheet. Columns: `#`, Company, Priority, Region, Country, Offices / Cities, Company Type, Why it fits you, Your Min Ask (₹ LPA), Pay vs Your Min, Visa Route, Careers Page, Last Checked, Status, Notes.
- Add a re-import script so I can edit the Excel (add or remove companies) and re-sync without losing job history.
- For each company, store a detected `source_type` + `source_config` (see section 4) in a version-controlled config file (e.g. `companies.yaml`) so fixes are easy to review.

## 4. Fetching jobs: reliability first

Scraping 100 different HTML career sites is brittle, so use this order of preference:

1. **Public ATS JSON APIs (preferred, no HTML scraping):**
   - Greenhouse: `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`
   - Lever: `api.lever.co/v0/postings/{company}?mode=json`
   - Ashby: `api.ashbyhq.com/posting-api/job-board/{name}`
   - SmartRecruiters: `api.smartrecruiters.com/v1/companies/{id}/postings`
   - Workable: `apply.workable.com/api/v3/accounts/{account}/jobs`
   - Workday: the `/wday/cxs/{tenant}/{site}/jobs` POST endpoint
   - Others you find (Eightfold, Phenom, Oracle HCM, iCIMS, Pinpoint, SuccessFactors, company JSON endpoints such as amazon.jobs `search.json`).
   - Hints I already know: Tekion and PayPay use Greenhouse; Meesho uses Lever; Freshworks uses SmartRecruiters; Hugging Face uses Workable; Tabby uses Pinpoint; talabat and Delivery Hero use careers.deliveryhero.com.
2. **Auto-detection script:** for each careers URL, follow redirects and inspect the page and network calls to detect the ATS and its token. Write the result to `companies.yaml`. **Verify every adapter against the live endpoint** and report which companies are covered.
3. **Fallback for sites with no usable API:** a headless-browser adapter (Playwright) that loads the listing page, filtered by keyword where the site supports URL filters, and extracts title, location and URL. Optionally use an LLM to parse messy HTML.
4. **Last resort:** mark the company `manual` and show it in a "check manually" list on the dashboard with its careers link. Don't silently drop any company.

**Rules:**
- Only public, logged-out pages. No LinkedIn, Naukri or Indeed scraping. Respect robots.txt and terms of service.
- Rate-limit politely (1–2 s between requests per domain), set a clear User-Agent, and add retries with backoff.
- Pre-filter by title and location *before* fetching full job descriptions, to keep runs fast.
- Deduplicate by a stable key: company + ATS job id, or normalized URL.
- A job is **"new"** the first run it's seen. Track `first_seen`, `last_seen`, and mark `closed` when it disappears.

## 5. Matching & scoring

Two layers:

1. **Rule-based filter + base score (always on, free):** title keywords, exclusions, years-of-experience parsing from the description (regex for "X+ years", "X-Y years"), location match, salary check, visa/relocation phrases, priority boost.
2. **LLM fit score (optional, toggle via env):** use the Anthropic API with a small, cheap model (Claude Haiku, `claude-haiku-5-5`) **only on jobs that pass layer 1**. Return strict JSON: `{score 0-100, fit_summary (1 line), why_match [≤3 bullets], gaps [≤3 bullets], seniority_ok bool, visa_sponsorship: yes/no/unknown, est_years_required}`. Cache results per job so a job is never re-scored. Cap spend with a max number of LLM calls per run.

Final score = a weighted blend. Put the weights in config. Show the reasons on the dashboard so I understand every score.

## 6. Dashboard (UI must be clean and decent)

- **Stack suggestion:** Next.js (App Router) + TypeScript + Tailwind + shadcn/ui, deployed on Vercel. Choose something else only if you explain why in the plan.
- **Mobile-friendly:** I'll check it on my phone too. Light and dark mode.
- **Access:** password-protected, single user (password from env var, httpOnly session cookie). Not publicly indexable.

**Pages / views:**
1. **Today:** new matches since my last visit, sorted by score. Cards show: company + priority badge, title, location, region tag, score (colour-coded), one-line fit summary, posted/first-seen date, and an "Apply" button (opens the original posting). Expand a card to see why it matches, the gaps, and a description excerpt.
2. **All jobs:** a table with filters (region, country, company, priority, score range, status, "visa sponsored", date) and a search box.
3. **Tracker:** I set a status per job: New → Interested → Applied → Interviewing → Offer / Rejected / Not for me. Include a notes field and an applied date. Show it as a simple kanban or grouped list.
4. **Companies:** all 100 companies with source type, last successful fetch, open-job count, matches count, and **health** (✅ ok / ⚠️ failing / 📝 manual) with the error message. This is how I'll know when an adapter breaks.
5. **Stats strip:** new today, open matches, applied this week, companies failing.

"Not for me" hides a job permanently. A "seen" state clears the New badge.

## 7. Scheduling & deployment

- **Fetcher:** Python 3.12 (I know Python well). Use a `pyproject.toml` with uv or pip, plus typed, tested adapters.
- **Schedule:** GitHub Actions cron, **daily at 06:30 IST** (`0 1 * * *` UTC), plus a manual "Run now" button on the dashboard that triggers the workflow (`workflow_dispatch` via the GitHub API).
- **Database:** hosted Postgres on a free tier (Neon or Supabase). Run schema migrations through a tool, not hand-edited SQL.
- **Run logs:** store a summary per run (companies ok/failed, jobs found, new matches, LLM calls, duration).
- **Optional daily digest:** a Telegram bot message (preferred, free) or email with the top 5 new matches and a link to the dashboard. Toggle with env vars.
- **Secrets:** `DATABASE_URL`, `DASHBOARD_PASSWORD`, `ANTHROPIC_API_KEY` (optional), `GITHUB_TOKEN` for the Run-now button, `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` (optional). Keep them in GitHub Secrets and Vercel env vars; never commit them. Provide `.env.example`.
- **Private repo.** Ask me before creating any account, repo or deployment, and walk me through anything I have to click myself.

## 8. Phases (verify each before moving on)

1. Plan + repo skeleton + DB schema + Excel import → show me the companies table.
2. ATS detection + adapters → print a coverage report (how many companies on API, browser and manual) and a sample of fetched jobs.
3. Filtering + scoring → show me the top 20 matches from a real run, with the reasons for each.
4. Dashboard locally → screenshots or a run-through of each view.
5. Deploy (DB, Vercel, GitHub Actions) → confirm a scheduled run has populated the live dashboard.
6. README: setup, how to add or fix a company adapter, how to change filters and weights, cost notes, and troubleshooting.

## 9. Quality bar

- Tests for parsers and the scoring rules. Each adapter has a fixture-based test.
- One failing company must never break the whole run.
- Keep the code simple and readable. I'll maintain it myself.
- At the end, give me a short summary: the live URL, how to log in, coverage numbers, which companies are manual, and the expected monthly cost.
