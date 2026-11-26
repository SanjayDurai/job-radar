"use server";

import { eq } from "drizzle-orm";
import { refresh } from "next/cache";

import { db } from "@/db";
import { companies, jobs, tailoredResumes } from "@/db/schema";
import { requireSession } from "@/lib/auth";
import { getResumeMaster } from "@/lib/data";
import { tailorResume } from "@/lib/resume/tailor";
import type { TailorReport } from "@/lib/resume/types";
import { fitOnePage } from "@/lib/resume/verify";

export type TailorResult = { ok: true; id: number; score: number } | { ok: false; message: string };

/** "Tailor resume": rewrite the master resume for one job, check it, store it. ~20-40 s. */
export async function tailorResumeForJob(jobId: number): Promise<TailorResult> {
  await requireSession();
  try {
    const master = await getResumeMaster();
    if (!master) return { ok: false, message: "No master resume yet. Run `radar resume-upload` (see README, Tailored resumes)." };
    const [job] = await db
      .select({ title: jobs.title, description: jobs.description, company: companies.name })
      .from(jobs)
      .innerJoin(companies, eq(companies.id, jobs.companyId))
      .where(eq(jobs.id, jobId));
    if (!job) return { ok: false, message: "Job not found." };
    if (!job.description || job.description.length < 200)
      return { ok: false, message: "This job's description wasn't saved, so there's nothing to tailor against. Open the posting instead." };

    const out = await tailorResume(master, { title: job.title, company: job.company, description: job.description });
    const fit = await fitOnePage(out.resume, out.matched);
    const notes = [...out.notes];
    if (fit.trimmed.length) notes.push(`To fit one page, left out ${fit.trimmed.join(", ")}.`);
    if (!fit.readable) notes.push(`Some keywords didn't extract cleanly from the PDF (${fit.unreadable.join(", ")}): use the Word file.`);

    const report: TailorReport = {
      matched: out.matched,
      missing: out.missing,
      gaps: out.gaps,
      checks: [
        ...out.checks,
        { label: "PDF text is fully readable by software", ok: fit.readable },
        { label: "One page", ok: fit.pages === 1, detail: `${fit.pages} page${fit.pages === 1 ? "" : "s"}` },
      ],
      changes: out.changes,
      keywordScore: out.keywordScore,
      formatScore: out.formatScore,
      pdfReadable: fit.readable,
      pages: fit.pages,
      notes,
    };
    const [row] = await db
      .insert(tailoredResumes)
      .values({ jobId, model: out.model, content: fit.resume, keywords: out.keywords, scoreBefore: out.scoreBefore, scoreAfter: out.scoreAfter, report })
      .returning({ id: tailoredResumes.id });
    refresh();
    return { ok: true, id: row.id, score: out.scoreAfter };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const friendly = /429|rate limit/i.test(msg)
      ? "Groq's free per-minute limit was reached. Wait a minute and try again."
      : /GROQ_API_KEY/.test(msg)
        ? msg
        : `Tailoring failed: ${msg.slice(0, 200)}`;
    return { ok: false, message: friendly };
  }
}
