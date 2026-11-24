import { CircleAlertIcon, CircleCheckIcon, ExternalLinkIcon, NotebookPenIcon, CircleDashedIcon } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { PriorityTag } from "@/components/job-card";
import { getCompanies } from "@/lib/data";
import { COMPANY_REGION_LABELS, relativeDays, sourceKind } from "@/lib/format";

export const metadata = { title: "Companies" };

const HEALTH = {
  ok: { icon: CircleCheckIcon, label: "OK", className: "text-score-high" },
  failing: { icon: CircleAlertIcon, label: "Failing", className: "text-destructive" },
  manual: { icon: NotebookPenIcon, label: "Manual", className: "text-muted-foreground" },
  pending: { icon: CircleDashedIcon, label: "Not run yet", className: "text-muted-foreground" },
} as const;

function Health({ health }: { health: string }) {
  const h = HEALTH[health as keyof typeof HEALTH] ?? HEALTH.pending;
  return (
    <span className={`inline-flex items-center gap-1.5 text-sm font-medium ${h.className}`}>
      <h.icon className="size-4" aria-hidden />
      {h.label}
    </span>
  );
}

async function CompanyList() {
  const rows = await getCompanies();
  const manual = rows.filter((c) => c.health === "manual");
  const failing = rows.filter((c) => c.health === "failing");
  const counts = { ok: rows.filter((c) => c.health === "ok").length, failing: failing.length, manual: manual.length };
  return (
    <>
      <p className="mb-5 text-sm text-muted-foreground">
        {rows.length} companies: <span className="text-foreground">{counts.ok} fetched automatically</span>, {counts.failing} failing,{" "}
        {counts.manual} to check by hand.
      </p>

      {failing.length > 0 && (
        <section className="mb-6 rounded-lg border border-destructive/40 bg-destructive/5 p-4">
          <h2 className="font-semibold text-destructive">Failing on the last run</h2>
          <ul className="mt-2 space-y-1.5 text-sm">
            {failing.map((c) => (
              <li key={c.id}>
                <span className="font-medium">{c.name}</span>: <span className="text-muted-foreground">{c.lastError}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="mb-8">
        <h2 className="mb-2 font-semibold">Check by hand</h2>
        <p className="mb-3 text-sm text-muted-foreground">These sites can&apos;t be read automatically. Open them every few days.</p>
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {manual.map((c) => (
            <li key={c.id}>
              <a
                href={c.careersUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-between gap-2 rounded-md border bg-card px-3 py-2 text-sm hover:border-primary"
              >
                <span className="flex items-center gap-2">
                  {c.name} <PriorityTag priority={c.priority} />
                </span>
                <ExternalLinkIcon className="size-4 text-muted-foreground" aria-hidden />
              </a>
            </li>
          ))}
        </ul>
      </section>

      <h2 className="mb-2 font-semibold">All companies</h2>
      <div className="overflow-x-auto rounded-lg border bg-card">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">Company</th>
              <th className="px-3 py-2 font-medium">Region</th>
              <th className="px-3 py-2 font-medium">Source</th>
              <th className="px-3 py-2 font-medium">Health</th>
              <th className="px-3 py-2 font-medium">Last success</th>
              <th className="px-3 py-2 text-right font-medium">Listed</th>
              <th className="px-3 py-2 text-right font-medium">Matches</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {rows.map((c) => (
              <tr key={c.id}>
                <td className="px-3 py-2">
                  <a href={c.careersUrl} target="_blank" rel="noopener noreferrer" className="font-medium hover:underline">
                    {c.name}
                  </a>{" "}
                  <PriorityTag priority={c.priority} />
                  {c.lastError && c.health === "failing" && <p className="max-w-xs truncate text-xs text-destructive">{c.lastError}</p>}
                </td>
                <td className="px-3 py-2 text-muted-foreground">
                  {c.region === "abroad" ? c.country : COMPANY_REGION_LABELS[c.region]}
                </td>
                <td className="px-3 py-2 text-muted-foreground">
                  {sourceKind(c.sourceType)}
                  {sourceKind(c.sourceType) !== "Manual" && <span className="ml-1 text-xs">({c.sourceType})</span>}
                </td>
                <td className="px-3 py-2">
                  <Health health={c.health} />
                </td>
                <td className="px-3 py-2 text-muted-foreground">{c.lastSuccessAt ? relativeDays(c.lastSuccessAt) : "—"}</td>
                <td className="tnum px-3 py-2 text-right text-muted-foreground">{c.listed ?? "—"}</td>
                <td className="tnum px-3 py-2 text-right">
                  {Number(c.matches) > 0 ? (
                    <Link href={`/jobs?company=${c.slug}`} className="font-medium text-primary hover:underline">
                      {c.matches}
                    </Link>
                  ) : (
                    <span className="text-muted-foreground">0</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export default function CompaniesPage() {
  return (
    <>
      <h1 className="mb-1 text-2xl font-semibold tracking-tight">Companies</h1>
      <Suspense fallback={<div className="h-64 animate-pulse rounded-lg border bg-card" />}>
        <CompanyList />
      </Suspense>
    </>
  );
}
