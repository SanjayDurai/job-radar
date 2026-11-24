"use client";

import { ChevronDownIcon, ExternalLinkIcon } from "lucide-react";
import Link from "next/link";
import { useState, useTransition } from "react";
import { cn } from "cn";

import { markSeen, setStatus } from "@/app/actions";
import { ScoreDial } from "@/components/score-dial";
import { Button } from "@/components/ui/button";
import type { JobStatus } from "@/db/schema";
import { locationText, regionLabel, relativeDays } from "@/lib/format";
import type { JobItem } from "@/lib/data";

export function PriorityTag({ priority }: { priority: number }) {
  return (
    <span
      className={cn(
        "rounded px-1.5 py-0.5 text-xs font-medium",
        priority === 1 ? "bg-accent text-accent-foreground" : "bg-secondary text-muted-foreground",
      )}
      title={priority === 1 ? "P1 Dream company" : priority === 2 ? "P2 Strong" : "P3 Good"}
    >
      P{priority}
    </span>
  );
}

export function WhyThisScore({ job }: { job: JobItem }) {
  const llm = job.llmResult;
  return (
    <div className="grid gap-4 text-sm sm:grid-cols-2">
      {llm && (
        <>
          <div>
            <h4 className="mb-1.5 font-medium">Why it fits</h4>
            <ul className="space-y-1 text-muted-foreground">
              {llm.why_match.map((w) => (
                <li key={w} className="flex gap-2">
                  <span className="text-score-high" aria-hidden>+</span>
                  {w}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h4 className="mb-1.5 font-medium">Gaps</h4>
            <ul className="space-y-1 text-muted-foreground">
              {llm.gaps.map((g) => (
                <li key={g} className="flex gap-2">
                  <span className="text-score-low" aria-hidden>−</span>
                  {g}
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
      <div className="sm:col-span-2">
        <h4 className="mb-1.5 font-medium">
          Score breakdown
          <span className="ml-2 font-normal text-muted-foreground">
            rules {job.ruleScore}
            {job.llmScore != null && `, AI review ${job.llmScore}`}
          </span>
        </h4>
        <ul className="grid gap-x-6 gap-y-1 text-muted-foreground sm:grid-cols-2">
          {job.ruleReasons.map((r, i) => (
            <li key={i} className="flex justify-between gap-3">
              <span>{r.label}</span>
              {r.points !== 0 && (
                <span className={cn("tnum shrink-0", r.points > 0 ? "text-foreground" : "text-score-low")}>
                  {r.points > 0 ? `+${r.points}` : r.points}
                </span>
              )}
            </li>
          ))}
        </ul>
      </div>
      {job.excerpt && (
        <div className="sm:col-span-2">
          <h4 className="mb-1.5 font-medium">From the posting</h4>
          <p className="line-clamp-6 whitespace-pre-line text-muted-foreground">{job.excerpt}</p>
        </div>
      )}
    </div>
  );
}

/** A job on the Today list. Acting on it (seen, interested, not for me) removes it from the list. */
export function JobCard({ job }: { job: JobItem }) {
  const [open, setOpen] = useState(false);
  const [gone, setGone] = useState(false);
  const [pending, start] = useTransition();
  if (gone) return null;

  const act = (fn: () => Promise<void>) =>
    start(async () => {
      setGone(true);
      await fn();
    });
  const status = (s: JobStatus) => () => act(() => setStatus(job.id, s));
  const summary = job.llmResult?.fit_summary ?? job.ruleReasons.find((r) => r.points > 0 && r.label.startsWith("skills"))?.label;

  return (
    <article className={cn("rounded-lg border bg-card p-4 sm:p-5", pending && "opacity-60")}>
      <div className="flex gap-4">
        <ScoreDial score={job.finalScore} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
            <span className="font-medium">{job.companyName}</span>
            <PriorityTag priority={job.priority} />
            {job.belowPayBar && <span className="rounded bg-destructive/10 px-1.5 py-0.5 text-xs font-medium text-destructive">Below pay bar</span>}
            {job.visaSignal === "sponsored" && (
              <span className="rounded bg-score-high/10 px-1.5 py-0.5 text-xs font-medium text-score-high">Visa / relocation</span>
            )}
          </div>
          <h3 className="mt-1 text-[17px] leading-snug font-semibold text-balance">
            <Link href={`/jobs/${job.id}`} className="hover:underline focus-visible:underline focus-visible:outline-none">
              {job.title}
            </Link>
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {locationText(job.location, job.locations)}
            <span className="ml-2 text-foreground/70">({regionLabel(job.regionTag, job.country)})</span>
          </p>
          {summary && <p className="mt-2 max-w-prose text-[15px]">{summary}</p>}
          <p className="mt-2 text-xs text-muted-foreground">
            Found {relativeDays(job.firstSeen)}
            {job.yearsRequired != null && `, asks ${Number(job.yearsRequired)}+ years`}
          </p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button render={<a href={job.url} target="_blank" rel="noopener noreferrer" />} nativeButton={false} size="sm">
          Apply <ExternalLinkIcon aria-hidden />
        </Button>
        <Button variant="secondary" size="sm" onClick={status("interested")}>
          Interested
        </Button>
        <Button variant="ghost" size="sm" onClick={status("not_for_me")}>
          Not for me
        </Button>
        <Button variant="ghost" size="sm" onClick={() => act(() => markSeen([job.id]))}>
          Mark seen
        </Button>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="ml-auto flex items-center gap-1 rounded text-sm text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
        >
          Why this score
          <ChevronDownIcon className={cn("size-4 transition-transform", open && "rotate-180")} aria-hidden />
        </button>
      </div>

      {open && (
        <div className="mt-4 border-t pt-4">
          <WhyThisScore job={job} />
        </div>
      )}
    </article>
  );
}
