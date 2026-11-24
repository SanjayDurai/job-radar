import Link from "next/link";
import { Suspense } from "react";

import { markAllSeen } from "@/app/actions";
import { JobCard } from "@/components/job-card";
import { Button } from "@/components/ui/button";
import { getTodayJobs } from "@/lib/data";

export const metadata = { title: "Today" };

async function TodayList() {
  const { items, total } = await getTodayJobs();
  if (!items.length) {
    return (
      <div className="rounded-lg border border-dashed p-10 text-center">
        <p className="font-medium">You&apos;re caught up.</p>
        <p className="mt-1 text-sm text-muted-foreground">
          New matches land here after the 6:30 run. Older ones are in{" "}
          <Link href="/jobs" className="text-primary underline-offset-4 hover:underline">
            All jobs
          </Link>
          .
        </p>
      </div>
    );
  }
  return (
    <>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <p className="text-muted-foreground">
          <span className="tnum font-medium text-foreground">{total}</span> matches you haven&apos;t looked at yet, best first.
        </p>
        <form action={markAllSeen}>
          <Button type="submit" variant="outline" size="sm">
            Mark all seen
          </Button>
        </form>
      </div>
      <div className="space-y-3">
        {items.map((job) => (
          <JobCard key={job.id} job={job} />
        ))}
      </div>
      {total > items.length && (
        <p className="mt-6 text-center text-sm text-muted-foreground">
          Showing the top {items.length}.{" "}
          <Link href="/jobs?status=new" className="text-primary underline-offset-4 hover:underline">
            See all {total} unseen
          </Link>
        </p>
      )}
    </>
  );
}

function ListSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="h-40 animate-pulse rounded-lg border bg-card" />
      ))}
    </div>
  );
}

export default function TodayPage() {
  return (
    <div className="max-w-3xl">
      <h1 className="mb-1 text-2xl font-semibold tracking-tight">Today</h1>
      <Suspense fallback={<ListSkeleton />}>
        <TodayList />
      </Suspense>
    </div>
  );
}
