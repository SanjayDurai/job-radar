"use client";

import { useTransition } from "react";
import { cn } from "cn";
import { toast } from "sonner";

import { setStatus } from "@/app/actions";
import { JOB_STATUSES, type JobStatus } from "@/db/schema";
import { STATUS_LABELS } from "@/lib/format";

const TONE: Record<JobStatus, string> = {
  new: "bg-secondary text-muted-foreground",
  interested: "bg-accent text-accent-foreground",
  applied: "bg-primary/15 text-primary",
  interviewing: "bg-score-mid/15 text-score-mid",
  offer: "bg-score-high/15 text-score-high",
  rejected: "bg-destructive/10 text-destructive",
  not_for_me: "bg-secondary text-muted-foreground line-through",
};

export function StatusBadge({ status }: { status: JobStatus }) {
  return <span className={cn("rounded px-1.5 py-0.5 text-xs font-medium", TONE[status])}>{STATUS_LABELS[status]}</span>;
}

/** Native select (good on phones); changing it saves immediately. */
export function StatusSelect({ jobId, status, className }: { jobId: number; status: JobStatus; className?: string }) {
  const [pending, start] = useTransition();
  return (
    <select
      aria-label="Status"
      value={status}
      disabled={pending}
      onChange={(e) => {
        const next = e.target.value as JobStatus;
        start(async () => {
          await setStatus(jobId, next);
          toast.success(`Moved to ${STATUS_LABELS[next]}`);
        });
      }}
      className={cn(
        "h-8 rounded-md border border-input bg-card px-2 text-sm focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-60",
        className,
      )}
    >
      {JOB_STATUSES.map((s) => (
        <option key={s} value={s}>
          {STATUS_LABELS[s]}
        </option>
      ))}
    </select>
  );
}
