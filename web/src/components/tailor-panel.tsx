"use client";

import { CheckIcon, ChevronDownIcon, DownloadIcon, FileTextIcon, SparklesIcon, XIcon } from "lucide-react";
import { useState, useTransition } from "react";
import { cn } from "cn";
import { toast } from "sonner";

import { tailorResumeForJob } from "@/app/resume-actions";
import { ScoreDial } from "@/components/score-dial";
import { Button } from "@/components/ui/button";
import { relativeDays, timeOfDay } from "@/lib/format";
import type { Keywords, TailorReport } from "@/lib/resume/types";

export type Version = { id: number; createdAt: Date; scoreBefore: number; scoreAfter: number; report: TailorReport; keywords: Keywords };

function Chips({ items, tone }: { items: string[]; tone: "ok" | "warn" | "muted" }) {
  if (!items.length) return <span className="text-sm text-muted-foreground">None</span>;
  return (
    <ul className="flex flex-wrap gap-1.5">
      {items.map((k) => (
        <li
          key={k}
          className={cn(
            "rounded px-1.5 py-0.5 text-xs font-medium",
            tone === "ok" && "bg-score-high/12 text-score-high",
            tone === "warn" && "bg-score-mid/15 text-score-mid",
            tone === "muted" && "bg-secondary text-muted-foreground",
          )}
        >
          {k}
        </li>
      ))}
    </ul>
  );
}

function Downloads({ id }: { id: number }) {
  return (
    <div className="flex flex-wrap gap-2">
      <Button render={<a href={`/api/resume/${id}?format=pdf`} />} nativeButton={false} size="sm">
        <DownloadIcon aria-hidden /> PDF
      </Button>
      <Button render={<a href={`/api/resume/${id}?format=docx`} />} nativeButton={false} size="sm" variant="secondary">
        <FileTextIcon aria-hidden /> Word (.docx)
      </Button>
    </div>
  );
}

function Result({ v }: { v: Version }) {
  const [showChanges, setShowChanges] = useState(false);
  const r = v.report;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-6">
        <div className="flex items-center gap-3">
          <ScoreDial score={v.scoreBefore} size={44} />
          <span className="text-sm text-muted-foreground">
            Your master
            <br />
            resume
          </span>
        </div>
        <span className="text-muted-foreground" aria-hidden>
          to
        </span>
        <div className="flex items-center gap-3">
          <ScoreDial score={v.scoreAfter} size={56} />
          <span className="text-sm">
            <span className="font-medium">Tailored</span>
            <br />
            <span className="text-muted-foreground">keywords {r.keywordScore}, format {r.formatScore}</span>
          </span>
        </div>
        <div className="ml-auto">
          <Downloads id={v.id} />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <h4 className="mb-1.5 text-sm font-medium">Job keywords on your resume</h4>
          <Chips items={r.matched} tone="ok" />
        </div>
        <div>
          <h4 className="mb-1.5 text-sm font-medium">You have these, not on this version</h4>
          <Chips items={r.missing} tone="warn" />
        </div>
        <div>
          <h4 className="mb-1.5 text-sm font-medium">Gaps (not in your master, never added)</h4>
          <Chips items={r.gaps} tone="muted" />
        </div>
      </div>

      <ul className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
        {r.checks.map((c) => (
          <li key={c.label} className="flex items-start gap-2">
            {c.ok ? <CheckIcon className="mt-0.5 size-4 shrink-0 text-score-high" aria-label="Passed" /> : <XIcon className="mt-0.5 size-4 shrink-0 text-destructive" aria-label="Failed" />}
            <span>
              {c.label}
              {c.detail && <span className="text-muted-foreground"> ({c.detail})</span>}
            </span>
          </li>
        ))}
      </ul>

      {r.notes.length > 0 && (
        <ul className="space-y-1 rounded-md bg-muted/60 p-3 text-sm text-muted-foreground">
          {r.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}

      {r.changes.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setShowChanges((o) => !o)}
            aria-expanded={showChanges}
            className="flex items-center gap-1 text-sm font-medium hover:underline focus-visible:outline-2 focus-visible:outline-ring"
          >
            What changed ({r.changes.length})
            <ChevronDownIcon className={cn("size-4 transition-transform", showChanges && "rotate-180")} aria-hidden />
          </button>
          {showChanges && (
            <ul className="mt-3 space-y-3 text-sm">
              {r.changes.map((c, i) => (
                <li key={i} className="rounded-md border p-3">
                  <p className="mb-1 text-xs text-muted-foreground">{c.section}</p>
                  <p className="text-muted-foreground line-through decoration-muted-foreground/50">{c.before}</p>
                  <p className="mt-1">{c.after.replace(/\*\*/g, "")}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export function TailorPanel({ jobId, versions, hasMaster }: { jobId: number; versions: Version[]; hasMaster: boolean }) {
  const [pending, start] = useTransition();
  const [latest, ...older] = versions;
  const run = () =>
    start(async () => {
      const res = await tailorResumeForJob(jobId);
      if (res.ok) toast.success(`Resume tailored: score ${res.score}`);
      else toast.error(res.message, { duration: 10_000 });
    });

  return (
    <section id="resume" className="scroll-mt-20 rounded-lg border bg-card p-4 sm:p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold">Tailored resume</h2>
          <p className="text-sm text-muted-foreground">
            Rewrites your master resume for this job using only facts already in it, then checks it the way an ATS would.
          </p>
        </div>
        <Button onClick={run} disabled={pending || !hasMaster}>
          <SparklesIcon className={pending ? "animate-pulse" : undefined} aria-hidden />
          {pending ? "Tailoring… about 30 s" : latest ? "Tailor again" : "Tailor my resume"}
        </Button>
      </div>
      {!hasMaster && (
        <p className="text-sm text-muted-foreground">
          Upload your master resume first: <code className="rounded bg-muted px-1">python -m uv run radar resume-upload</code> (see README).
        </p>
      )}
      {latest && <Result v={latest} />}
      {older.length > 0 && (
        <div className="mt-5 border-t pt-4">
          <h3 className="mb-2 text-sm font-medium">Earlier versions</h3>
          <ul className="space-y-2 text-sm">
            {older.map((v) => (
              <li key={v.id} className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-muted-foreground">
                  {relativeDays(v.createdAt)} at {timeOfDay(new Date(v.createdAt))}, score <span className="tnum font-medium text-foreground">{v.scoreAfter}</span>
                </span>
                <Downloads id={v.id} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
