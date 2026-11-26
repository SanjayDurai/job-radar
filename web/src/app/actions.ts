"use server";

import { sql } from "drizzle-orm";
import { refresh } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { db } from "@/db";
import { JOB_STATUSES, jobState, type JobStatus } from "@/db/schema";
import { requireSession } from "@/lib/auth";
import { SESSION_COOKIE, createSessionToken, timingSafeEqual } from "@/lib/session";


export async function login(_prev: { error?: string } | undefined, form: FormData) {
  const expected = process.env.DASHBOARD_PASSWORD ?? "";
  const given = String(form.get("password") ?? "");
  if (!expected) return { error: "DASHBOARD_PASSWORD isn't set on the server." };
  if (!timingSafeEqual(given, expected)) {
    await new Promise((r) => setTimeout(r, 800)); // slow down guessing
    return { error: "Wrong password." };
  }
  const { token, expires } = await createSessionToken();
  (await cookies()).set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    expires,
  });
  const next = String(form.get("next") ?? "/");
  redirect(next.startsWith("/") && !next.startsWith("//") ? next : "/");
}

export async function logout() {
  (await cookies()).delete(SESSION_COOKIE);
  redirect("/login");
}

export async function setStatus(jobId: number, status: JobStatus) {
  await requireSession();
  if (!JOB_STATUSES.includes(status)) throw new Error(`Unknown status ${status}`);
  await db
    .insert(jobState)
    .values({ jobId, status, seenAt: new Date(), appliedOn: status === "applied" ? sql`current_date` : null })
    .onConflictDoUpdate({
      target: jobState.jobId,
      set: {
        status,
        seenAt: sql`coalesce(${jobState.seenAt}, now())`,
        // first move to "applied" records today's date; later moves keep it
        appliedOn: status === "applied" ? sql`coalesce(${jobState.appliedOn}, current_date)` : sql`${jobState.appliedOn}`,
        updatedAt: sql`now()`,
      },
    });
  refresh();
}

export async function markSeen(jobIds: number[]) {
  await requireSession();
  if (!jobIds.length) return;
  await db
    .insert(jobState)
    .values(jobIds.map((jobId) => ({ jobId, status: "new" as const, seenAt: new Date() })))
    .onConflictDoUpdate({ target: jobState.jobId, set: { seenAt: sql`coalesce(${jobState.seenAt}, now())`, updatedAt: sql`now()` } });
  refresh();
}

export async function markAllSeen() {
  await requireSession();
  await db.execute(sql`
    insert into job_state (job_id, status, seen_at, updated_at)
    select j.id, 'new', now(), now()
    from jobs j join job_scores s on s.job_id = j.id
    left join job_state st on st.job_id = j.id
    where j.is_open and not s.excluded and st.seen_at is null
    on conflict (job_id) do update set seen_at = now(), updated_at = now()`);
  refresh();
}

export async function saveTrackerDetails(jobId: number, notes: string, appliedOn: string | null) {
  await requireSession();
  const date = appliedOn && /^\d{4}-\d{2}-\d{2}$/.test(appliedOn) ? appliedOn : null;
  await db
    .insert(jobState)
    .values({ jobId, status: "interested", notes: notes.slice(0, 5000), appliedOn: date, seenAt: new Date() })
    .onConflictDoUpdate({ target: jobState.jobId, set: { notes: notes.slice(0, 5000), appliedOn: date, updatedAt: sql`now()` } });
  refresh();
}

/** "Run now": starts the GitHub Actions workflow (needs GITHUB_TOKEN + GITHUB_REPO on the server). */
export async function runNow(): Promise<{ ok: boolean; message: string }> {
  await requireSession();
  const token = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO;
  if (!token || !repo) return { ok: false, message: "Run now isn't set up yet: add GITHUB_TOKEN and GITHUB_REPO." };
  const res = await fetch(`https://api.github.com/repos/${repo}/actions/workflows/daily.yml/dispatches`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" },
    body: JSON.stringify({ ref: process.env.GITHUB_REF_NAME ?? "main", inputs: { trigger: "manual" } }),
  });
  if (res.status === 204) return { ok: true, message: "Run started. New jobs appear in about 15 minutes." };
  return { ok: false, message: `GitHub refused the run (HTTP ${res.status}). Check the token's Actions permission.` };
}
