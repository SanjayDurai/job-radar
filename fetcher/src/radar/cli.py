"""Command line entry point:  `uv run radar --help`."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import typer
from alembic import command
from alembic.config import Config
from rich.console import Console
from rich.table import Table
from sqlalchemy import func, select

from radar.db import session_scope
from radar.excel_import import SheetError, import_excel
from radar.models import Company, CompanyRun, Job
from radar.profile import experience_years
from radar.settings import DEFAULT_XLSX

app = typer.Typer(help="Personal Job Radar", no_args_is_help=True)
console = Console()

FETCHER_DIR = Path(__file__).resolve().parents[2]
HEALTH_ICON = {"ok": "✅", "failing": "⚠️", "manual": "📝", "pending": "…"}


@app.command("db-upgrade")
def db_upgrade() -> None:
    """Apply all database migrations (alembic upgrade head)."""
    cfg = Config(str(FETCHER_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(FETCHER_DIR / "migrations"))
    command.upgrade(cfg, "head")
    console.print("[green]Database is up to date.[/green]")


@app.command("import-excel")
def import_excel_cmd(xlsx: Path = typer.Option(DEFAULT_XLSX, help="Path to the companies workbook")) -> None:
    """Sync the Companies sheet into the database and config/companies.yaml (job history is kept)."""
    try:
        with session_scope() as s:
            summary = import_excel(s, xlsx)
    except SheetError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e
    console.print(
        f"[green]Imported.[/green] added={len(summary.added)} updated={len(summary.updated)} "
        f"unchanged={summary.unchanged} deactivated={len(summary.deactivated)} "
        f"reactivated={len(summary.reactivated)}"
    )
    for label, names in (("Added", summary.added), ("Removed from sheet (kept, inactive)", summary.deactivated)):
        if names and len(names) <= 20:
            console.print(f"  {label}: {', '.join(names)}")


@app.command("companies")
def companies_cmd(
    region: str | None = typer.Option(None, help="chennai | india_other | india_remote | abroad | remote_global"),
    include_inactive: bool = typer.Option(False, help="Also show companies removed from the sheet"),
) -> None:
    """Print the companies table."""
    with session_scope() as s:
        q = select(Company).order_by(Company.sheet_no)
        if region:
            q = q.where(Company.region == region)
        if not include_inactive:
            q = q.where(Company.active.is_(True))
        companies = list(s.scalars(q))
        open_counts = dict(s.execute(select(Job.company_id, func.count()).where(Job.is_open).group_by(Job.company_id)).all())

    table = Table(title=f"Companies ({len(companies)})", show_lines=False, header_style="bold")
    for col in ("#", "Company", "Pri", "Region", "Country", "Min ₹LPA", "Source", "Health", "Open jobs"):
        table.add_column(col, overflow="fold")
    for c in companies:
        table.add_row(
            str(c.sheet_no or ""),
            c.name,
            f"P{c.priority}",
            c.region,
            c.country,
            f"{c.min_ask_lpa.normalize():f}" if c.min_ask_lpa is not None else "",
            c.source_type,
            HEALTH_ICON.get(c.health, c.health),
            str(open_counts.get(c.id, 0)),
        )
    console.print(table)
    console.print("By region: " + ", ".join(f"{k}={v}" for k, v in Counter(c.region for c in companies).most_common()))
    console.print("By priority: " + ", ".join(f"P{k}={v}" for k, v in sorted(Counter(c.priority for c in companies).items())))
    console.print("By source: " + ", ".join(f"{k}={v}" for k, v in Counter(c.source_type for c in companies).most_common()))


@app.command("detect")
def detect_cmd(
    only: list[str] = typer.Option(None, help="Company slug(s) to detect; default = all still 'unknown'"),
    all_companies: bool = typer.Option(False, "--all", help="Re-detect every company (report only)"),
    write: bool = typer.Option(True, help="Write verified results into config/companies.yaml"),
) -> None:
    """Detect each company's ATS from its careers page and verify against the live API."""
    from radar.companies_config import load_companies_yaml, save_companies_yaml
    from radar.detect import detect_all, write_report

    entries = load_companies_yaml()
    targets = [
        (slug, e["name"], e["careers_url"])
        for slug, e in entries.items()
        if e.get("in_sheet", True)
        and ((only and slug in only) or (not only and (all_companies or e.get("source_type") == "unknown")))
    ]
    console.print(f"Detecting {len(targets)} companies (polite: 1.2 s between requests per host)…")
    results = detect_all(targets)
    write_report(results)

    table = Table(title="Detection", header_style="bold")
    for col in ("Company", "Best", "Config", "Jobs", "Other signals / error"):
        table.add_column(col, overflow="fold")
    updated = 0
    review: list[str] = []
    for d in results:
        best = d.best
        others = sorted({c.source_type for c in d.candidates if c is not best})
        table.add_row(
            d.name,
            best.source_type if best else "-",
            json.dumps(best.source_config) if best else "",
            "" if not best or best.verified_jobs is None else str(best.verified_jobs),
            ", ".join(others) or (d.error or ""),
        )
        if not (best and best.verified_jobs):
            continue
        if best.found_on == "name-guess":
            # A guessed board name can belong to a different company (e.g. "applied" = Applied Intuition),
            # so these are never written automatically: check with `radar try` and edit the YAML yourself.
            review.append(f"{d.slug}: {best.source_type} {json.dumps(best.source_config)} ({best.verified_jobs} jobs)")
        elif write and not all_companies:
            entries[d.slug]["source_type"] = best.source_type
            entries[d.slug]["source_config"] = best.source_config
            entries[d.slug]["notes"] = f"auto-detected ({best.found_on}); {best.verified_jobs} open jobs at detection"
            updated += 1
    console.print(table)
    if write and updated:
        save_companies_yaml(entries)
    console.print(f"Verified + written: {updated}. Full report: config/detect_report.json")
    if review:
        console.print("[yellow]Name-guess matches to check by hand (not written):[/yellow]\n  " + "\n  ".join(review))


@app.command("try")
def try_cmd(
    slug: str,
    show: int = typer.Option(8, help="How many sample jobs to print"),
    describe: bool = typer.Option(False, help="Also fetch the first job's description"),
) -> None:
    """Run one company's adapter live (from config/companies.yaml) without touching the database."""
    import time

    from radar.adapters import FetchContext, get_adapter
    from radar.companies_config import load_companies_yaml
    from radar.http import PoliteClient

    entry = load_companies_yaml().get(slug)
    if not entry:
        console.print(f"[red]No company '{slug}' in companies.yaml[/red]")
        raise typer.Exit(1)
    adapter = get_adapter(entry.get("source_type", ""))
    if adapter is None:
        console.print(f"[yellow]{slug}: source_type '{entry.get('source_type')}' has no adapter[/yellow]")
        raise typer.Exit(1)
    t0 = time.monotonic()
    with PoliteClient() as client:
        ctx = FetchContext(client=client)
        jobs = adapter.list_jobs(entry.get("source_config") or {}, ctx)
        console.print(
            f"[green]{entry['name']}[/green] via {adapter.source_type}: {len(jobs)} jobs "
            f"in {time.monotonic() - t0:.1f}s ({client.request_count} requests)"
        )
        for j in jobs[:show]:
            console.print(
                f"  • {j.title}  [dim]| {j.all_locations_text()[:80]} | {j.posted_at:%Y-%m-%d}[/dim]"
                if j.posted_at
                else f"  • {j.title}  [dim]| {j.all_locations_text()[:80]}[/dim]"
            )
            console.print(f"    [dim]{j.url}[/dim]")
        if describe and jobs:
            desc = adapter.fetch_description(jobs[0], entry.get("source_config") or {}, ctx)
            console.print(f"\n[bold]Description of first job[/bold] ({len(desc or '')} chars):\n{(desc or '')[:700]}")


@app.command("run")
def run_cmd(
    only: list[str] = typer.Option(None, help="Only these company slugs"),
    trigger: str = typer.Option("local", help="local | schedule | manual (recorded on the run)"),
    workers: int = typer.Option(6, help="Companies fetched in parallel (per-host politeness still applies)"),
    verbose: bool = typer.Option(False, "-v", help="Log each company as it finishes"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip the LLM layer this run"),
) -> None:
    """Fetch all active companies, store matching jobs, score them, update health and the run log."""
    import logging

    from radar.run import run_all

    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per request is too noisy
    run = run_all(trigger=trigger, only=only, workers=workers, use_llm=not no_llm)
    console.print(
        f"[bold]Run #{run.id}[/bold] {run.status} in {run.duration_s}s — companies ok={run.companies_ok} "
        f"failed={run.companies_failed} manual={run.companies_manual}; listed={run.jobs_found}, "
        f"new jobs={run.jobs_new}, new matches={run.matches_new}, LLM calls={run.llm_calls}"
    )
    if run.details:
        console.print(f"[dim]{json.dumps(run.details)}[/dim]")


@app.command("score")
def score_cmd(no_llm: bool = typer.Option(False, "--no-llm", help="Rules only")) -> None:
    """Re-score all open jobs (e.g. after editing config/scoring.yaml) without fetching."""
    from radar.scoring.llm import LLMScorer
    from radar.scoring.pipeline import score_open_jobs
    from radar.settings import profile, scoring

    with session_scope() as s:
        llm = None if no_llm else LLMScorer(scoring(), profile())
        stats = score_open_jobs(s, llm)
    console.print(
        f"Scored {stats.scored} open jobs ({stats.excluded} excluded). LLM: {stats.llm_calls} calls, "
        f"{stats.llm_cached} cached, {stats.llm_errors} errors. {stats.llm_note or ''}"
    )


@app.command("llm-models")
def llm_models_cmd() -> None:
    """List the models your Groq key can use (to pick `llm.model` in config/scoring.yaml)."""
    import os

    from groq import Groq

    if not os.environ.get("GROQ_API_KEY"):
        console.print("[yellow]GROQ_API_KEY is not set in .env[/yellow]")
        raise typer.Exit(1)
    for m in sorted(Groq(api_key=os.environ["GROQ_API_KEY"]).models.list().data, key=lambda m: m.id):
        console.print(f"  {m.id}")


@app.command("top")
def top_cmd(
    n: int = typer.Option(20, help="How many jobs"),
    region: str | None = typer.Option(None, help="Filter by company region"),
    reasons: bool = typer.Option(True, help="Show the reasons behind each score"),
) -> None:
    """Best open matches, highest score first, with the reasons for each score."""
    from radar.models import JobScore

    with session_scope() as s:
        q = (
            select(Job, Company, JobScore)
            .join(Company, Company.id == Job.company_id)
            .join(JobScore, JobScore.job_id == Job.id)
            .where(Job.is_open, JobScore.excluded.is_(False))
            .order_by(JobScore.final_score.desc(), Job.first_seen.desc())
            .limit(n)
        )
        if region:
            q = q.where(Company.region == region)
        rows = list(s.execute(q).all())
    for i, (job, company, sc) in enumerate(rows, 1):
        colour = "green" if sc.final_score >= 70 else "yellow" if sc.final_score >= 50 else "red"
        flags = " [red]below pay bar[/red]" if sc.below_pay_bar else ""
        console.print(
            f"\n[bold]{i:>2}. [{colour}]{sc.final_score:>3}[/{colour}][/bold]  [bold]{job.title}[/bold] — {company.name} "
            f"[dim](P{company.priority}, {company.region})[/dim]{flags}"
        )
        loc = " | ".join(x for x in [job.location, *(job.locations or [])] if x) or "location not stated"
        yrs = f"{sc.years_required:g}+ yrs" if sc.years_required is not None else "yrs n/a"
        console.print(f"     [dim]{loc[:90]} · {yrs} · visa: {sc.visa_signal} · {job.url}[/dim]")
        if sc.llm_result:
            console.print(f"     [cyan]LLM {sc.llm_score}:[/cyan] {sc.llm_result.get('fit_summary', '')}")
        if reasons:
            parts = [f"{r['label']} ({r['points']:+d})" if r["points"] else r["label"] for r in sc.rule_reasons]
            console.print("     " + "; ".join(parts))


SOURCE_KIND = {
    **dict.fromkeys(
        [
            "greenhouse",
            "lever",
            "ashby",
            "smartrecruiters",
            "workable",
            "pinpoint",
            "workday",
            "oracle_hcm",
            "eightfold",
            "amazon",
            "atlassian",
            "phonepe",
            "mercari",
            "jibe",
            "emirates",
        ],
        "API (JSON)",
    ),  # fmt: skip
    **dict.fromkeys(["html_links", "sitemap", "google"], "HTML / sitemap"),
    "playwright": "Browser (Playwright)",
    "manual": "Manual",
    "unknown": "Manual",
}


@app.command("coverage")
def coverage_cmd(samples: int = typer.Option(15, help="Sample matched jobs to print")) -> None:
    """Coverage report: how each company is fetched, its health, and a sample of stored jobs."""
    with session_scope() as s:
        companies = list(s.scalars(select(Company).where(Company.active.is_(True)).order_by(Company.sheet_no)))
        open_counts = dict(s.execute(select(Job.company_id, func.count()).where(Job.is_open).group_by(Job.company_id)).all())
        last = {}
        for cr in s.scalars(select(CompanyRun).order_by(CompanyRun.id)):
            last[cr.company_id] = cr
        sample = s.execute(
            select(Job.title, Job.location, Company.name, Job.url)
            .join(Company)
            .where(Job.is_open)
            .order_by(func.random())
            .limit(samples)
        ).all()

    kinds = Counter(SOURCE_KIND.get(c.source_type, "Other") for c in companies)
    console.print("[bold]Coverage[/bold]: " + ", ".join(f"{k} = {v}" for k, v in kinds.most_common()))
    health = Counter(c.health for c in companies)
    console.print("Health: " + ", ".join(f"{HEALTH_ICON.get(k, k)} {k} = {v}" for k, v in health.most_common()))

    table = Table(header_style="bold", title="Per company (last run)")
    for col in ("Company", "Kind", "Source", "Health", "Listed", "Matched (open)", "Note / error"):
        table.add_column(col, overflow="fold")
    for c in companies:
        cr = last.get(c.id)
        table.add_row(
            c.name,
            SOURCE_KIND.get(c.source_type, "Other"),
            c.source_type,
            HEALTH_ICON.get(c.health, c.health),
            str(cr.jobs_found) if cr else "",
            str(open_counts.get(c.id, 0)),
            (c.last_error or "")[:90],
        )
    console.print(table)
    manual = [c.name for c in companies if c.source_type in ("manual", "unknown")]
    console.print(f"[bold]Manual ({len(manual)}):[/bold] {', '.join(manual)}")
    console.print("\n[bold]Sample of stored (pre-filtered) open jobs[/bold]")
    for title, loc, company, _url in sample:
        console.print(f"  • [green]{company}[/green] — {title}  [dim]| {loc or '-'}[/dim]")


@app.command("resume-upload")
def resume_upload_cmd(file: Path = typer.Option(None, help="Path to master.yaml (default resume/master.yaml)")) -> None:
    """Validate your master resume and store it in the database for the dashboard's 'Tailor resume'."""
    from radar.resume import MASTER_PATH, ResumeError, load_master, upload_master

    try:
        master = load_master(file or MASTER_PATH)
    except ResumeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e
    with session_scope() as s:
        bullets = upload_master(s, master)
    n_skills = sum(len(v) for v in master["skills"].values())
    console.print(f"[green]Master resume uploaded[/green]: {bullets} bullets, {n_skills} skills.")


@app.command("experience")
def experience_cmd() -> None:
    """Show my experience in years, computed from career_start in config/profile.yaml."""
    console.print(f"{experience_years()} years")


if __name__ == "__main__":
    app()
