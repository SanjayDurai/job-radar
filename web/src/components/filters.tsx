import Link from "next/link";

import { Button } from "@/components/ui/button";
import type { JobFilters } from "@/lib/data";
import { COMPANY_REGION_LABELS, STATUS_LABELS } from "@/lib/format";

const field =
  "h-9 rounded-md border border-input bg-card px-2.5 text-sm text-foreground focus-visible:outline-2 focus-visible:outline-ring";

function Select({
  name,
  label,
  value,
  options,
  emptyLabel = "Any",
}: {
  name: string;
  label: string;
  value?: string;
  options: [string, string][];
  emptyLabel?: string;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-muted-foreground">
      {label}
      <select name={name} defaultValue={value ?? ""} className={field}>
        <option value="">{emptyLabel}</option>
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </label>
  );
}

/** A plain GET form: filters live in the URL, so every view is bookmarkable and works without JS. */
export function JobFiltersForm({
  f,
  companies,
  countries,
}: {
  f: JobFilters;
  companies: { slug: string; name: string }[];
  countries: string[];
}) {
  return (
    <form method="get" className="rounded-lg border bg-card p-3 sm:p-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <label className="col-span-2 flex flex-col gap-1 text-xs text-muted-foreground sm:col-span-3 lg:col-span-2">
          Search title or company
          <input type="search" name="q" defaultValue={f.q} placeholder="e.g. applied scientist" className={field} />
        </label>
        <Select name="region" label="Region" value={f.region} options={Object.entries(COMPANY_REGION_LABELS)} />
        <Select name="country" label="Country" value={f.country} options={countries.map((c) => [c, c])} />
        <Select name="company" label="Company" value={f.company} options={companies.map((c) => [c.slug, c.name])} />
        <Select name="priority" label="Priority" value={f.priority} options={[["1", "P1 Dream"], ["2", "P2 Strong"], ["3", "P3 Good"]]} />
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Score from
          <input type="number" name="min" min={0} max={100} defaultValue={f.min} placeholder="0" className={field} />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Score to
          <input type="number" name="max" min={0} max={100} defaultValue={f.max} placeholder="100" className={field} />
        </label>
        <Select name="status" label="Status" value={f.status} options={Object.entries(STATUS_LABELS)} />
        <Select name="since" label="Found within" value={f.since} options={[["1", "1 day"], ["3", "3 days"], ["7", "7 days"], ["30", "30 days"]]} />
        <Select name="visa" label="Visa" value={f.visa} options={[["sponsored", "Mentions sponsorship"]]} />
        <Select
          name="sort"
          label="Sort by"
          value={f.sort}
          emptyLabel="Best score"
          options={[["new", "Newest first"], ["company", "Company"]]}
        />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
        <label className="flex items-center gap-2">
          <input type="checkbox" name="excluded" value="1" defaultChecked={f.excluded === "1"} className="size-4 accent-primary" />
          Include excluded
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" name="closed" value="1" defaultChecked={f.closed === "1"} className="size-4 accent-primary" />
          Include closed
        </label>
        <div className="ml-auto flex gap-2">
          <Button render={<Link href="/jobs" />} nativeButton={false} variant="ghost" size="sm">
            Clear
          </Button>
          <Button type="submit" size="sm">
            Apply filters
          </Button>
        </div>
      </div>
    </form>
  );
}
