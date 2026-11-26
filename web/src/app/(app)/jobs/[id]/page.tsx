import { ExternalLinkIcon } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { PriorityTag, WhyThisScore } from "@/components/job-card";
import { ScoreDial } from "@/components/score-dial";
import { StatusSelect } from "@/components/status";
import { TailorPanel } from "@/components/tailor-panel";
import { TrackerDetailsForm } from "@/components/tracker-details";
import { Button } from "@/components/ui/button";
import { getJob, getResumeMaster, getTailoredResumes } from "@/lib/data";
import { locationText, regionLabel, relativeDays, shortDate } from "@/lib/format";

export const metadata = { title: "Job" };
// "Tailor resume" makes 2-3 AI calls and renders a PDF: allow up to 2 minutes for this page's actions.
export const maxDuration = 120;

async function JobDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const job = Number.isFinite(Number(id)) ? await getJob(Number(id)) : null;
  if (!job) notFound();
  const [versions, master] = await Promise.all([getTailoredResumes(job.id), getResumeMaster()]);
  return (
    <article className="max-w-3xl">
      <Link href="/jobs" className="text-sm text-muted-foreground hover:text-foreground">
        All jobs
      </Link>
      <div className="mt-3 flex gap-4">
        <ScoreDial score={job.finalScore} size={64} />
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">{job.companyName}</span>
            <PriorityTag priority={job.priority} />
            {job.excluded && <span className="text-destructive">Excluded: {job.excludeReason}</span>}
            {!job.isOpen && <span className="text-muted-foreground">Closed {relativeDays(job.closedAt)}</span>}
          </div>
          <h1 className="mt-1 text-2xl leading-tight font-semibold tracking-tight text-balance">{job.title}</h1>
          <p className="mt-1 text-muted-foreground">
            {locationText(job.location, job.locations)} ({regionLabel(job.regionTag, job.country)})
          </p>
        </div>
      </div>

      {job.llmResult?.fit_summary && <p className="mt-5 text-[17px]">{job.llmResult.fit_summary}</p>}

      <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-muted-foreground">Found</dt>
          <dd>{shortDate(job.firstSeen)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Experience asked</dt>
          <dd>{job.yearsRequired != null ? `${Number(job.yearsRequired)}+ years` : "Not stated"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Visa</dt>
          <dd>{job.visaSignal === "sponsored" ? "Sponsorship mentioned" : job.visaSignal === "right_to_work_required" ? "Right to work needed" : "Not mentioned"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Posted pay</dt>
          <dd className={job.belowPayBar ? "text-destructive" : undefined}>
            {job.salaryLpa != null ? `₹${Number(job.salaryLpa)} LPA${job.belowPayBar ? ", below your bar" : ""}` : "Not shown"}
          </dd>
        </div>
      </dl>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <Button render={<a href={job.url} target="_blank" rel="noopener noreferrer" />} nativeButton={false}>
          Open the posting <ExternalLinkIcon aria-hidden />
        </Button>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          Status
          <StatusSelect jobId={job.id} status={job.status} />
        </label>
      </div>

      <div className="mt-8">
        <TailorPanel jobId={job.id} versions={versions} hasMaster={Boolean(master)} />
      </div>

      <section className="mt-6 rounded-lg border bg-card p-4 sm:p-5">
        <h2 className="mb-3 font-semibold">Tracking</h2>
        <TrackerDetailsForm jobId={job.id} notes={job.notes} appliedOn={job.appliedOn} />
      </section>

      <section className="mt-6 rounded-lg border bg-card p-4 sm:p-5">
        <h2 className="mb-3 font-semibold">Why this score</h2>
        <WhyThisScore job={{ ...job, excerpt: null }} />
      </section>

      {job.description && (
        <section className="mt-6">
          <h2 className="mb-2 font-semibold">Description</h2>
          <div className="max-w-prose text-[15px] leading-relaxed whitespace-pre-line text-foreground/90">{job.description}</div>
        </section>
      )}
    </article>
  );
}

export default function JobPage({ params }: PageProps<"/jobs/[id]">) {
  return (
    <Suspense fallback={<div className="h-96 max-w-3xl animate-pulse rounded-lg border bg-card" />}>
      <JobDetail params={params} />
    </Suspense>
  );
}
