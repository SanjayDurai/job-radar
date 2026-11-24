import Link from "next/link";

import { RunNowButton } from "@/components/run-now";
import { relativeDays } from "@/lib/format";
import { getStats } from "@/lib/data";

function Stat({ value, label, href, alert }: { value: number; label: string; href: string; alert?: boolean }) {
  return (
    <Link href={href} className="group flex items-baseline gap-1.5 rounded-sm focus-visible:outline-2 focus-visible:outline-ring">
      <span className={`tnum text-lg font-semibold ${alert ? "text-destructive" : "text-foreground"}`}>{value}</span>
      <span className="text-sm text-muted-foreground group-hover:text-foreground">{label}</span>
    </Link>
  );
}

export async function StatsStrip() {
  const s = await getStats();
  const run = s.lastRun;
  const runText = run
    ? `Last run ${relativeDays(run.startedAt)} at ${run.startedAt.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}${run.status === "ok" ? "" : `, ${run.status}`}`
    : "No runs yet";
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
      <Stat value={s.newToday} label="new today" href="/jobs?since=1&sort=new" />
      <Stat value={s.openMatches} label="open matches" href="/jobs" />
      <Stat value={s.appliedThisWeek} label="applied this week" href="/tracker" />
      <Stat value={s.companiesFailing} label="companies failing" href="/companies" alert={s.companiesFailing > 0} />
      <div className="ml-auto flex items-center gap-3">
        <span className="hidden text-sm text-muted-foreground sm:inline">{runText}</span>
        <RunNowButton />
      </div>
    </div>
  );
}

export function StatsStripSkeleton() {
  return <div className="h-8 w-full max-w-xl animate-pulse rounded bg-muted" />;
}
