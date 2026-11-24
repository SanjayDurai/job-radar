import Link from "next/link";
import { Suspense } from "react";

import { ScoreDial } from "@/components/score-dial";
import { StatusSelect } from "@/components/status";
import { TRACKER_STATUSES, getTrackerJobs } from "@/lib/data";
import { STATUS_LABELS, shortDate } from "@/lib/format";

export const metadata = { title: "Tracker" };

async function Board() {
  const jobs = await getTrackerJobs();
  if (!jobs.length) {
    return (
      <div className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
        Nothing tracked yet. Mark a job <span className="font-medium text-foreground">Interested</span> on Today and it shows up here.
      </div>
    );
  }
  return (
    // Columns side by side on wide screens (scrolls sideways if needed); stacked groups on phones.
    <div className="grid gap-4 md:auto-cols-[minmax(240px,1fr)] md:grid-flow-col md:overflow-x-auto md:pb-2">
      {TRACKER_STATUSES.map((status) => {
        const col = jobs.filter((j) => j.status === status);
        return (
          <section key={status} aria-label={STATUS_LABELS[status]} className="min-w-0 rounded-lg bg-muted/60 p-2">
            <h2 className="flex items-center justify-between px-1.5 py-1 text-sm font-semibold">
              {STATUS_LABELS[status]}
              <span className="tnum font-normal text-muted-foreground">{col.length}</span>
            </h2>
            <ul className="mt-1 space-y-2">
              {col.map((j) => (
                <li key={j.id} className="rounded-md border bg-card p-3">
                  <div className="flex gap-3">
                    <ScoreDial score={j.finalScore} size={36} />
                    <div className="min-w-0">
                      <Link href={`/jobs/${j.id}`} className="block text-sm leading-snug font-medium hover:underline">
                        {j.title}
                      </Link>
                      <p className="text-xs text-muted-foreground">{j.companyName}</p>
                    </div>
                  </div>
                  {j.appliedOn && <p className="mt-2 text-xs text-muted-foreground">Applied {shortDate(j.appliedOn)}</p>}
                  {j.notes && <p className="mt-1 line-clamp-2 text-xs">{j.notes}</p>}
                  <StatusSelect jobId={j.id} status={j.status} className="mt-2 h-7 w-full text-xs" />
                </li>
              ))}
              {!col.length && <li className="px-1.5 py-2 text-xs text-muted-foreground">None</li>}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

export default function TrackerPage() {
  return (
    <>
      <h1 className="mb-1 text-2xl font-semibold tracking-tight">Tracker</h1>
      <p className="mb-4 text-sm text-muted-foreground">Change a job&apos;s status to move it. Add notes and the applied date on the job&apos;s page.</p>
      <Suspense fallback={<div className="h-64 animate-pulse rounded-lg bg-muted" />}>
        <Board />
      </Suspense>
    </>
  );
}
