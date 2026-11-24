// Mirrors the tables created by the Python Alembic migrations (fetcher/migrations).
// Python owns the schema; this file only describes it for typed queries. If you add a
// column in fetcher/src/radar/models.py, add it here too.
import {
  bigint,
  boolean,
  date,
  integer,
  jsonb,
  numeric,
  pgTable,
  smallint,
  text,
  timestamp,
  varchar,
} from "drizzle-orm/pg-core";

const ts = (name: string) => timestamp(name, { withTimezone: true, mode: "date" });

export const companies = pgTable("companies", {
  id: integer("id").primaryKey(),
  slug: varchar("slug", { length: 80 }).notNull(),
  sheetNo: integer("sheet_no"),
  name: varchar("name", { length: 200 }).notNull(),
  priority: smallint("priority").notNull(),
  priorityLabel: varchar("priority_label", { length: 40 }).notNull(),
  region: varchar("region", { length: 30 }).notNull(),
  regionLabel: varchar("region_label", { length: 80 }).notNull(),
  country: varchar("country", { length: 80 }).notNull(),
  cities: text("cities"),
  companyType: varchar("company_type", { length: 120 }),
  whyFit: text("why_fit"),
  minAskLpa: numeric("min_ask_lpa"),
  visaRoute: text("visa_route"),
  careersUrl: text("careers_url").notNull(),
  sourceType: varchar("source_type", { length: 40 }).notNull(),
  health: varchar("health", { length: 20 }).notNull(),
  lastAttemptAt: ts("last_attempt_at"),
  lastSuccessAt: ts("last_success_at"),
  lastError: text("last_error"),
  active: boolean("active").notNull(),
});

export const jobs = pgTable("jobs", {
  id: bigint("id", { mode: "number" }).primaryKey(),
  companyId: integer("company_id").notNull(),
  externalKey: varchar("external_key", { length: 300 }).notNull(),
  title: text("title").notNull(),
  location: text("location"),
  locations: jsonb("locations").$type<string[]>().notNull(),
  isRemote: boolean("is_remote").notNull(),
  url: text("url").notNull(),
  department: text("department"),
  employmentType: varchar("employment_type", { length: 80 }),
  description: text("description"),
  postedAt: ts("posted_at"),
  salaryMin: numeric("salary_min"),
  salaryMax: numeric("salary_max"),
  salaryCurrency: varchar("salary_currency", { length: 8 }),
  salaryPeriod: varchar("salary_period", { length: 16 }),
  passesFilter: boolean("passes_filter").notNull(),
  firstSeen: ts("first_seen").notNull(),
  lastSeen: ts("last_seen").notNull(),
  closedAt: ts("closed_at"),
  isOpen: boolean("is_open").notNull(),
});

export type Reason = { label: string; points: number };
export type LlmResult = {
  score: number;
  fit_summary: string;
  why_match: string[];
  gaps: string[];
  seniority_ok: boolean;
  visa_sponsorship: "yes" | "no" | "unknown";
  est_years_required: number | null;
};

export const jobScores = pgTable("job_scores", {
  jobId: bigint("job_id", { mode: "number" }).primaryKey(),
  ruleScore: smallint("rule_score").notNull(),
  ruleReasons: jsonb("rule_reasons").$type<Reason[]>().notNull(),
  regionTag: varchar("region_tag", { length: 30 }),
  belowPayBar: boolean("below_pay_bar").notNull(),
  yearsRequired: numeric("years_required"),
  visaSignal: varchar("visa_signal", { length: 30 }),
  salaryLpa: numeric("salary_lpa"),
  excluded: boolean("excluded").notNull(),
  excludeReason: text("exclude_reason"),
  llmScore: smallint("llm_score"),
  llmResult: jsonb("llm_result").$type<LlmResult | null>(),
  llmModel: varchar("llm_model", { length: 80 }),
  finalScore: smallint("final_score").notNull(),
  scoredAt: ts("scored_at").notNull(),
});

export const JOB_STATUSES = ["new", "interested", "applied", "interviewing", "offer", "rejected", "not_for_me"] as const;
export type JobStatus = (typeof JOB_STATUSES)[number];

export const jobState = pgTable("job_state", {
  jobId: bigint("job_id", { mode: "number" }).primaryKey(),
  status: varchar("status", { length: 20 }).$type<JobStatus>().notNull(),
  notes: text("notes"),
  appliedOn: date("applied_on", { mode: "string" }),
  seenAt: ts("seen_at"),
  updatedAt: ts("updated_at").notNull().defaultNow(),
});

export const runs = pgTable("runs", {
  id: integer("id").primaryKey(),
  trigger: varchar("trigger", { length: 20 }).notNull(),
  status: varchar("status", { length: 20 }).notNull(),
  startedAt: ts("started_at").notNull(),
  finishedAt: ts("finished_at"),
  durationS: integer("duration_s"),
  companiesTotal: integer("companies_total").notNull(),
  companiesOk: integer("companies_ok").notNull(),
  companiesFailed: integer("companies_failed").notNull(),
  companiesManual: integer("companies_manual").notNull(),
  jobsFound: integer("jobs_found").notNull(),
  jobsNew: integer("jobs_new").notNull(),
  matchesNew: integer("matches_new").notNull(),
  llmCalls: integer("llm_calls").notNull(),
  error: text("error"),
  details: jsonb("details").$type<Record<string, unknown>>().notNull(),
});

export const companyRuns = pgTable("company_runs", {
  id: bigint("id", { mode: "number" }).primaryKey(),
  runId: integer("run_id").notNull(),
  companyId: integer("company_id").notNull(),
  status: varchar("status", { length: 20 }).notNull(),
  jobsFound: integer("jobs_found").notNull(),
  jobsMatched: integer("jobs_matched").notNull(),
  error: text("error"),
  createdAt: ts("created_at").notNull(),
});
