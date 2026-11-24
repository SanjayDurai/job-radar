# Personal Job Radar

Every morning at 06:30 IST, a GitHub Action checks the careers pages of my ~100 target companies
(from `Job_Switch_Top100_Companies.xlsx`), keeps the openings that fit my profile, scores them
(rules + a free Groq LLM review), and shows them on a private dashboard. Everything runs on free tiers.

```
GitHub Actions (daily 06:30 IST)                 Vercel (Singapore)
  fetcher/  ── fetch 86 companies ──┐               web/  Next.js dashboard
            ── filter + score ─────▶ Neon Postgres ◀── reads / saves your status + notes
            ── Groq LLM review                (Singapore)
```

---

## 1. Finish the deployment (one time, ~10 minutes)

The database (Neon) is set up and already holds all jobs. Two copy-paste steps are left, because they
need you signed in. The values are prepared for you in two **git-ignored** files in this folder:
`github-secrets.env` and `vercel.env`. Open them in Notepad.

### a) GitHub: add 2 secrets (lets the daily run write to the database)
1. Open https://github.com/SanjayDurai/job-radar/settings/secrets/actions
2. **New repository secret** → Name `DATABASE_URL`, Secret: the line under `# Name: DATABASE_URL` in `github-secrets.env` → **Add secret**.
3. Again for `GROQ_API_KEY` (the line under `# Name: GROQ_API_KEY`).
4. Test it: **Actions** tab → **Daily job radar** → **Run workflow** → **Run workflow**. It takes about 15–20 minutes; a green tick means it worked.

### b) Vercel: deploy the dashboard
1. Go to https://vercel.com/new and sign in (GitHub sign-in is easiest).
2. Next to **job-radar**, click **Import**. (If it isn't listed: **Adjust GitHub App Permissions** → give Vercel access to `job-radar`.)
3. **Root Directory**: click **Edit** → choose **`web`**. Framework is detected as Next.js.
4. Open **Environment Variables**, copy *all* lines of `vercel.env` (Ctrl+A, Ctrl+C) and paste them into the first **Key** box. Vercel splits them into separate variables.
5. Click **Deploy**. After ~2 minutes you get a URL like `https://job-radar-xxxx.vercel.app`. That's your dashboard.
6. Sign in with the `DASHBOARD_PASSWORD` from `vercel.env`. (Change it any time in Vercel → Project → Settings → Environment Variables, then **Redeploy**.)

From then on, every `git push` to `main` redeploys the dashboard automatically.

### c) Optional: make the "Run now" button work
1. https://github.com/settings/personal-access-tokens/new → *Fine-grained token*.
2. Name `job-radar run now`, expiration 1 year, **Repository access: Only select repositories → job-radar**.
3. **Permissions → Repository permissions → Actions: Read and write**. Generate and copy the token.
4. In Vercel → Project → Settings → Environment Variables, add `GITHUB_TOKEN` = the token. **Redeploy**.

---

## 2. Daily use (5–10 minutes a morning)

The run finishes around **06:45–07:00 IST**. On your phone or laptop, open the dashboard.

1. **Glance at the strip at the top**: *new today*, *open matches*, *applied this week*, *companies failing*.
2. **Today**: unseen matches, best first. For each card:
   - Read the one-line verdict. Tap **Why this score** for "why it fits", the gaps, and every rule point.
   - **Apply** opens the real posting. Apply there, then set the job's status to **Applied** (on its page).
   - **Interested** keeps it in the Tracker. **Not for me** hides it forever. **Mark seen** just clears it from Today.
   - Done for the day? **Mark all seen**.
3. **Tracker**: your pipeline: Interested → Applied → Interviewing → Offer / Rejected. Open a job to add notes (referral, recruiter, interview dates) and the applied date.
4. **All jobs**: search and filter everything (e.g. Region *Abroad* + Visa *Mentions sponsorship*, or Company *Google*). Filters are in the URL, so bookmark the views you like.
5. **Companies**, about once a week:
   - **Check by hand**: 14 sites that can't be read automatically (Walmart, Goldman Sachs, Flipkart, Canva, …). Open each link every few days.
   - **Failing** (red panel): a site changed. Usually a quick fix, see *Fixing a company* below.

**Scores:** green 70+ = strong, amber 50–69 = possible, below 50 hidden from Today.
Jobs asking 5+ years, senior titles and citizen-only roles are excluded automatically
(still visible in All jobs with *Include excluded*).

**Tips**
- Your experience (1.3 years) is computed from `career_start` in `config/profile.yaml`, so scoring keeps up as you grow.
- Most jobs show "Location unclear" or no salary; that's normal. Posted salaries below your floor are flagged *Below pay bar*.
- If a job looks wrongly scored, the reasons on its page show exactly which rule did it. Tweak `config/scoring.yaml`.

---

## 3. Changing filters, weights and companies

| What | Where | After editing |
|---|---|---|
| Title keywords, exclusions, pay floors, citizenship phrases | `config/profile.yaml` | commit + push; applies on the next run |
| Score points, skill keywords, FX rates, LLM model and call cap | `config/scoring.yaml` | same (or run `radar score` locally against Neon) |
| Add/remove companies | `Job_Switch_Top100_Companies.xlsx` | push; each run re-imports it. New companies start as `unknown`: run `radar detect` (below) |
| How a company is fetched | `config/companies.yaml` | push |

### Fixing or adding a company
Every company's fetch settings live in [`config/companies.yaml`](config/companies.yaml).

1. `python -m uv run radar detect --only <slug>`: scans the careers page for a known ATS and verifies it live.
   Verified matches are written to the YAML. *Name-guess* matches are only printed, because they can be a different company.
2. Or edit the entry by hand:

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
   | `manual` | `{}`: shown in "Check by hand"; put the reason in `notes` |
3. `python -m uv run radar try <slug> --describe`: runs just that company live and prints sample jobs.
4. Commit + push. `python -m uv run radar coverage` shows every company's source, health and last error.

Rules the fetcher always follows: public logged-out pages only, robots.txt respected (RFC 9309), 1.2 s
between requests per site, a clear User-Agent, no LinkedIn/Naukri/Indeed, no bot-check bypassing.

---

## 4. Cost: ₹0 / month

| Service | Free tier | This project uses |
|---|---|---|
| GitHub Actions (private repo) | 2,000 min/month | ~20 min/day ≈ 600 min |
| Neon Postgres | 0.5 GB, scales to zero | a few MB |
| Vercel Hobby | personal projects | one small dashboard |
| Groq | 1,000 requests/day, 8,000 tokens/min | ≤ 60 requests/run |

No card is attached anywhere, so nothing can be charged. If a limit is reached, things degrade gracefully
(e.g. the LLM step stops for the day and jobs keep their rule scores).

---

## 5. Troubleshooting

| Symptom | Fix |
|---|---|
| Daily run shows a red ✗ in Actions | Open the run log. "DATABASE_URL is not set" means a missing secret (1a). Otherwise the last step shows which company failed; one bad company never stops the others. |
| A company shows **Failing** | Its site changed. `radar try <slug>` to see the error, then fix its entry (section 3). |
| Dashboard says "DATABASE_URL is not set" | Add the env vars in Vercel (1b) and redeploy. |
| "Run now isn't set up yet" | Add `GITHUB_TOKEN` (1c). |
| No AI review on some jobs | The LLM reviews up to 60 of the best new jobs per run; the rest get reviewed on later runs. |
| Groq model removed | `python -m uv run radar llm-models` lists current ones; set `llm.model` in `config/scoring.yaml`. |
| Forgot the dashboard password | It's in Vercel → Settings → Environment Variables (and in `vercel.env`). |

---

## 6. Local development (Windows)

```powershell
pip install --user uv
Copy-Item .env.example .env          # local settings (git-ignored)
.\scripts\localdb.ps1 init           # private Postgres on port 5433 (after a reboot: .\scripts\localdb.ps1 start)

cd fetcher
python -m uv sync
python -m uv run radar db-upgrade
python -m uv run radar import-excel
python -m uv run radar run -v        # full fetch + score into the local database
python -m uv run radar top --n 20    # best matches with reasons
python -m uv run pytest              # tests (set TEST_DATABASE_URL=postgresql://radar@localhost:5433/radar_test for DB tests)

cd ..\web
npm install
npm run dev                          # http://localhost:3000 (settings in web/.env.local)
```

To run any `radar` command against the live database instead, set `DATABASE_URL` to the Neon URL for that command.

## Layout

| Path | What |
|---|---|
| `config/profile.yaml` | experience start date, skills, title keywords, exclusions, pay floors |
| `config/scoring.yaml` | score weights, skill keywords, FX table, LLM settings |
| `config/companies.yaml` | how each company is fetched (ATS type + token) |
| `fetcher/` | Python 3.12: Excel import, adapters, scoring, CLI (`radar --help`) |
| `fetcher/migrations/` | Alembic schema migrations (the only place the schema changes) |
| `web/` | Next.js 16 dashboard (`web/src/db/schema.ts` mirrors the Alembic tables) |
| `.github/workflows/` | `daily.yml` (06:30 IST fetch, also "Run now"), `ci.yml` (tests on push) |
