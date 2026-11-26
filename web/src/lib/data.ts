import "server-only";

import { and, asc, count, desc, eq, gte, ilike, inArray, isNull, lte, ne, notInArray, or, sql, type SQL } from "drizzle-orm";
import { connection } from "next/server";

import { db } from "@/db";
import { appState, companies, companyRuns, jobScores, jobState, jobs, runs, tailoredResumes, type JobStatus } from "@/db/schema";
import type { MasterResume } from "@/lib/resume/types";

/** A job counts as a "match" from this score up (same idea as new_match_min_score in scoring.yaml). */
export const MATCH_MIN_SCORE = 50;
export const PAGE_SIZE = 50;

const jobFields = {
  id: jobs.id,
  title: jobs.title,
  url: jobs.url,
  location: jobs.location,
  locations: jobs.locations,
  isRemote: jobs.isRemote,
  firstSeen: jobs.firstSeen,
  postedAt: jobs.postedAt,
  isOpen: jobs.isOpen,
  closedAt: jobs.closedAt,
  excerpt: sql<string | null>`left(${jobs.description}, 1400)`,
  companyName: companies.name,
  companySlug: companies.slug,
  priority: companies.priority,
  region: companies.region,
  country: companies.country,
  finalScore: jobScores.finalScore,
  ruleScore: jobScores.ruleScore,
  llmScore: jobScores.llmScore,
  llmResult: jobScores.llmResult,
  ruleReasons: jobScores.ruleReasons,
  regionTag: jobScores.regionTag,
  belowPayBar: jobScores.belowPayBar,
  yearsRequired: jobScores.yearsRequired,
  visaSignal: jobScores.visaSignal,
  salaryLpa: jobScores.salaryLpa,
  excluded: jobScores.excluded,
  excludeReason: jobScores.excludeReason,
  status: sql<JobStatus>`coalesce(${jobState.status}, 'new')`,
  seenAt: jobState.seenAt,
  notes: jobState.notes,
  appliedOn: jobState.appliedOn,
};

export type JobItem = Awaited<ReturnType<typeof getTodayJobs>>["items"][number];

function baseJobQuery() {
  return db
    .select(jobFields)
    .from(jobs)
    .innerJoin(companies, eq(companies.id, jobs.companyId))
    .innerJoin(jobScores, eq(jobScores.jobId, jobs.id))
    .leftJoin(jobState, eq(jobState.jobId, jobs.id));
}

const notHidden = or(isNull(jobState.status), ne(jobState.status, "not_for_me"));

/** Today: matches I haven't looked at yet, best first. */
export async function getTodayJobs(limit = 60) {
  await connection();
  const where = and(
    eq(jobs.isOpen, true),
    eq(jobScores.excluded, false),
    gte(jobScores.finalScore, MATCH_MIN_SCORE),
    isNull(jobState.seenAt),
    or(isNull(jobState.status), eq(jobState.status, "new")),
  );
  const [items, [{ total }]] = await Promise.all([
    baseJobQuery().where(where).orderBy(desc(jobScores.finalScore), desc(jobs.firstSeen)).limit(limit),
    db
      .select({ total: count() })
      .from(jobs)
      .innerJoin(jobScores, eq(jobScores.jobId, jobs.id))
      .leftJoin(jobState, eq(jobState.jobId, jobs.id))
      .where(where),
  ]);
  return { items, total };
}

export type JobFilters = {
  q?: string;
  region?: string;
  country?: string;
  company?: string;
  priority?: string;
  min?: string;
  max?: string;
  status?: string;
  visa?: string;
  since?: string;
  excluded?: string;
  closed?: string;
  sort?: string;
  page?: string;
};

export async function getJobs(f: JobFilters) {
  await connection();
  const conds: (SQL | undefined)[] = [];
  if (f.closed !== "1") conds.push(eq(jobs.isOpen, true));
  if (f.excluded !== "1") conds.push(eq(jobScores.excluded, false));
  if (f.q) conds.push(or(ilike(jobs.title, `%${f.q}%`), ilike(companies.name, `%${f.q}%`)));
  if (f.region) conds.push(eq(companies.region, f.region));
  if (f.country) conds.push(eq(companies.country, f.country));
  if (f.company) conds.push(eq(companies.slug, f.company));
  if (f.priority) conds.push(eq(companies.priority, Number(f.priority)));
  if (f.min) conds.push(gte(jobScores.finalScore, Number(f.min)));
  if (f.max) conds.push(lte(jobScores.finalScore, Number(f.max)));
  if (f.visa === "sponsored") conds.push(eq(jobScores.visaSignal, "sponsored"));
  if (f.since) conds.push(gte(jobs.firstSeen, sql`now() - make_interval(days => ${Number(f.since)})`));
  if (f.status === "new") conds.push(or(isNull(jobState.status), eq(jobState.status, "new")));
  else if (f.status) conds.push(eq(jobState.status, f.status as JobStatus));
  else conds.push(notHidden);
  const where = and(...conds);
  const page = Math.max(1, Number(f.page) || 1);
  const order =
    f.sort === "new"
      ? [desc(jobs.firstSeen), desc(jobScores.finalScore)]
      : f.sort === "company"
        ? [asc(companies.name), desc(jobScores.finalScore)]
        : [desc(jobScores.finalScore), desc(jobs.firstSeen)];
  const [items, [{ total }]] = await Promise.all([
    baseJobQuery().where(where).orderBy(...order).limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE),
    db
      .select({ total: count() })
      .from(jobs)
      .innerJoin(companies, eq(companies.id, jobs.companyId))
      .innerJoin(jobScores, eq(jobScores.jobId, jobs.id))
      .leftJoin(jobState, eq(jobState.jobId, jobs.id))
      .where(where),
  ]);
  return { items, total, page, pages: Math.max(1, Math.ceil(total / PAGE_SIZE)) };
}

export async function getJob(id: number) {
  await connection();
  const [item] = await baseJobQuery().where(eq(jobs.id, id)).limit(1);
  if (!item) return null;
  const [full] = await db.select({ description: jobs.description, department: jobs.department, employmentType: jobs.employmentType }).from(jobs).where(eq(jobs.id, id));
  return { ...item, ...full };
}

export const TRACKER_STATUSES: JobStatus[] = ["interested", "applied", "interviewing", "offer", "rejected"];

export async function getTrackerJobs() {
  await connection();
  return baseJobQuery()
    .where(inArray(jobState.status, TRACKER_STATUSES))
    .orderBy(desc(jobState.updatedAt));
}

export async function getFilterOptions() {
  await connection();
  const rows = await db
    .select({ slug: companies.slug, name: companies.name, country: companies.country })
    .from(companies)
    .where(eq(companies.active, true))
    .orderBy(asc(companies.name));
  return { companies: rows, countries: [...new Set(rows.map((r) => r.country))].sort() };
}

export async function getCompanies() {
  await connection();
  const lastRun = db
    .selectDistinctOn([companyRuns.companyId], {
      companyId: companyRuns.companyId,
      status: companyRuns.status,
      jobsFound: companyRuns.jobsFound,
      createdAt: companyRuns.createdAt,
    })
    .from(companyRuns)
    .orderBy(companyRuns.companyId, desc(companyRuns.id))
    .as("last_run");
  const matchCounts = db
    .select({
      companyId: jobs.companyId,
      open: count().as("open"),
      matches: sql<number>`count(*) filter (where ${jobScores.finalScore} >= ${MATCH_MIN_SCORE} and not ${jobScores.excluded})`.as("matches"),
    })
    .from(jobs)
    .innerJoin(jobScores, eq(jobScores.jobId, jobs.id))
    .where(eq(jobs.isOpen, true))
    .groupBy(jobs.companyId)
    .as("match_counts");
  return db
    .select({
      id: companies.id,
      slug: companies.slug,
      name: companies.name,
      priority: companies.priority,
      region: companies.region,
      country: companies.country,
      careersUrl: companies.careersUrl,
      sourceType: companies.sourceType,
      health: companies.health,
      lastSuccessAt: companies.lastSuccessAt,
      lastError: companies.lastError,
      listed: lastRun.jobsFound,
      open: sql<number>`coalesce(${matchCounts.open}, 0)`,
      matches: sql<number>`coalesce(${matchCounts.matches}, 0)`,
    })
    .from(companies)
    .leftJoin(lastRun, eq(lastRun.companyId, companies.id))
    .leftJoin(matchCounts, eq(matchCounts.companyId, companies.id))
    .where(eq(companies.active, true))
    .orderBy(asc(companies.sheetNo));
}

export async function getResumeMaster(): Promise<MasterResume | null> {
  const [row] = await db.select({ value: appState.value }).from(appState).where(eq(appState.key, "resume_master"));
  const m = row?.value as (Omit<MasterResume, "skills"> & { skills: MasterResume["skills"] | Record<string, string[]> }) | undefined;
  if (!m) return null;
  // Older uploads stored skills as an object (whose key order JSONB doesn't keep)
  const skills = Array.isArray(m.skills) ? m.skills : Object.entries(m.skills).map(([group, items]) => ({ group, items }));
  return { ...m, skills };
}

/** Tailored resumes for a job, newest first (content omitted: only needed for downloads). */
export async function getTailoredResumes(jobId: number) {
  await connection();
  return db
    .select({
      id: tailoredResumes.id,
      createdAt: tailoredResumes.createdAt,
      scoreBefore: tailoredResumes.scoreBefore,
      scoreAfter: tailoredResumes.scoreAfter,
      report: tailoredResumes.report,
      keywords: tailoredResumes.keywords,
    })
    .from(tailoredResumes)
    .where(eq(tailoredResumes.jobId, jobId))
    .orderBy(desc(tailoredResumes.id));
}

export async function getTailoredResume(id: number) {
  const [row] = await db
    .select({ content: tailoredResumes.content, title: jobs.title, company: companies.name })
    .from(tailoredResumes)
    .innerJoin(jobs, eq(jobs.id, tailoredResumes.jobId))
    .innerJoin(companies, eq(companies.id, jobs.companyId))
    .where(eq(tailoredResumes.id, id));
  return row ?? null;
}

export async function getStats() {
  await connection();
  const matchOpen = and(eq(jobs.isOpen, true), eq(jobScores.excluded, false), gte(jobScores.finalScore, MATCH_MIN_SCORE));
  const [[newToday], [openMatches], [appliedWeek], [failing], [lastRun]] = await Promise.all([
    db
      .select({ n: count() })
      .from(jobs)
      .innerJoin(jobScores, eq(jobScores.jobId, jobs.id))
      .where(and(matchOpen, gte(jobs.firstSeen, sql`now() - interval '24 hours'`))),
    db
      .select({ n: count() })
      .from(jobs)
      .innerJoin(jobScores, eq(jobScores.jobId, jobs.id))
      .leftJoin(jobState, eq(jobState.jobId, jobs.id))
      .where(and(matchOpen, or(isNull(jobState.status), notInArray(jobState.status, ["not_for_me", "rejected"])))),
    db
      .select({ n: count() })
      .from(jobState)
      .where(and(inArray(jobState.status, ["applied", "interviewing", "offer"]), gte(jobState.appliedOn, sql`(current_date - 7)`))),
    db.select({ n: count() }).from(companies).where(and(eq(companies.active, true), eq(companies.health, "failing"))),
    db.select().from(runs).orderBy(desc(runs.id)).limit(1),
  ]);
  return {
    newToday: newToday.n,
    openMatches: openMatches.n,
    appliedThisWeek: appliedWeek.n,
    companiesFailing: failing.n,
    lastRun: lastRun ?? null,
  };
}
