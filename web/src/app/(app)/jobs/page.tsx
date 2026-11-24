import Link from "next/link";
import { Suspense } from "react";

import { CollapsibleFilters } from "@/components/collapsible-filters";
import { JobFiltersForm } from "@/components/filters";
import { PriorityTag } from "@/components/job-card";
import { ScoreDial } from "@/components/score-dial";
import { StatusBadge } from "@/components/status";
import { getFilterOptions, getJobs, type JobFilters } from "@/lib/data";
import { locationText, regionLabel, relativeDays } from "@/lib/format";

export const metadata = { title: "All jobs" };

function pageHref(f: JobFilters, page: number) {
  const params = new URLSearchParams(Object.entries({ ...f, page: String(page) }).filter(([, v]) => v) as [string, string][]);
  return `/jobs?${params}`;
}

async function Results({ searchParams }: { searchParams: Promise<JobFilters> }) {
  const f = await searchParams;
  const [{ items, total, page, pages }, opts] = await Promise.all([getJobs(f), getFilterOptions()]);
  return (
    <>
      <CollapsibleFilters activeCount={Object.entries(f).filter(([k, v]) => v && k !== "page").length}>
        <JobFiltersForm f={f} companies={opts.companies} countries={opts.countries} />
      </CollapsibleFilters>
      <p className="mt-4 mb-2 text-sm text-muted-foreground">
        <span className="tnum font-medium text-foreground">{total}</span> jobs
        {pages > 1 && `, page ${page} of ${pages}`}
      </p>

      {items.length === 0 ? (
        <div className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
          No jobs match these filters. Try widening the score range or clearing a filter.
        </div>
      ) : (
        <>
          {/* Phones: compact list */}
          <ul className="divide-y rounded-lg border bg-card md:hidden">
            {items.map((j) => (
              <li key={j.id}>
                <Link href={`/jobs/${j.id}`} className="flex gap-3 p-3">
                  <ScoreDial score={j.finalScore} size={40} />
                  <div className="min-w-0">
                    <p className="font-medium leading-snug">{j.title}</p>
                    <p className="text-sm text-muted-foreground">
                      {j.companyName}, {regionLabel(j.regionTag, j.country)}
                    </p>
                    <p className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                      <StatusBadge status={j.status} />
                      {relativeDays(j.firstSeen)}
                    </p>
                  </div>
                </Link>
              </li>
            ))}
          </ul>

          {/* Wider screens: table */}
          <div className="hidden overflow-hidden rounded-lg border bg-card md:block">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="w-16 px-3 py-2 font-medium">Score</th>
                  <th className="px-3 py-2 font-medium">Role</th>
                  <th className="px-3 py-2 font-medium">Location</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 text-right font-medium">Found</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {items.map((j) => (
                  <tr key={j.id} className={j.excluded || !j.isOpen ? "opacity-60" : undefined}>
                    <td className="px-3 py-2">
                      <ScoreDial score={j.finalScore} size={38} />
                    </td>
                    <td className="max-w-md px-3 py-2">
                      <Link href={`/jobs/${j.id}`} className="font-medium hover:underline">
                        {j.title}
                      </Link>
                      <div className="mt-0.5 flex items-center gap-2 text-muted-foreground">
                        {j.companyName} <PriorityTag priority={j.priority} />
                        {j.excluded && <span className="text-xs">Excluded: {j.excludeReason}</span>}
                        {!j.isOpen && <span className="text-xs">Closed</span>}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                      <div className="text-foreground">{regionLabel(j.regionTag, j.country)}</div>
                      <div className="max-w-56 truncate text-xs">{locationText(j.location, j.locations)}</div>
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge status={j.status} />
                    </td>
                    <td className="tnum px-3 py-2 text-right whitespace-nowrap text-muted-foreground">{relativeDays(j.firstSeen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {pages > 1 && (
            <nav aria-label="Pages" className="mt-4 flex justify-between text-sm">
              {page > 1 ? (
                <Link href={pageHref(f, page - 1)} className="text-primary hover:underline">
                  Previous page
                </Link>
              ) : (
                <span />
              )}
              {page < pages && (
                <Link href={pageHref(f, page + 1)} className="text-primary hover:underline">
                  Next page
                </Link>
              )}
            </nav>
          )}
        </>
      )}
    </>
  );
}

export default function JobsPage({ searchParams }: PageProps<"/jobs">) {
  return (
    <>
      <h1 className="mb-4 text-2xl font-semibold tracking-tight">All jobs</h1>
      <Suspense fallback={<div className="h-64 animate-pulse rounded-lg border bg-card" />}>
        <Results searchParams={searchParams as Promise<JobFilters>} />
      </Suspense>
    </>
  );
}
