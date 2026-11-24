import type { JobStatus } from "@/db/schema";

export function scoreTone(score: number): "high" | "mid" | "low" {
  return score >= 70 ? "high" : score >= 50 ? "mid" : "low";
}

// The server (Vercel) runs in UTC, so every date is shown explicitly in India time.
export const TIME_ZONE = "Asia/Kolkata";
const IST_OFFSET_MS = 5.5 * 60 * 60 * 1000;
const istDay = (ms: number) => Math.floor((ms + IST_OFFSET_MS) / 86_400_000);

export function relativeDays(d: Date | string | null | undefined): string {
  if (!d) return "";
  const date = typeof d === "string" ? new Date(d) : d;
  const days = istDay(Date.now()) - istDay(date.getTime()); // calendar days in IST
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  return date.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: TIME_ZONE });
}

export function shortDate(d: Date | string | null | undefined): string {
  if (!d) return "";
  // A bare "YYYY-MM-DD" (applied date) is a calendar date: don't shift it across time zones
  const date = typeof d === "string" ? new Date(/^\d{4}-\d{2}-\d{2}$/.test(d) ? `${d}T12:00:00+05:30` : d) : d;
  return date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: TIME_ZONE });
}

export function timeOfDay(d: Date): string {
  return d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", timeZone: TIME_ZONE });
}

export function locationText(location: string | null, locations: string[] | null): string {
  const all = [location, ...(locations ?? [])].filter(Boolean) as string[];
  if (!all.length) return "Location not stated";
  return all.length > 2 ? `${all.slice(0, 2).join(", ")} +${all.length - 2} more` : all.join(", ");
}

/** Where the job sits relative to my location rules (from the job's region tag). */
export function regionLabel(tag: string | null, country: string): string {
  switch (tag) {
    case "chennai":
      return "Chennai";
    case "india_other":
      return "Other Indian city";
    case "india_remote":
      return "Remote from India";
    case "remote":
      return "Remote";
    case "abroad":
      return country;
    default:
      return "Location unclear";
  }
}

export const COMPANY_REGION_LABELS: Record<string, string> = {
  chennai: "Chennai",
  india_other: "Other Indian city",
  india_remote: "India, remote",
  abroad: "Abroad",
  remote_global: "Remote (global)",
};

export const STATUS_LABELS: Record<JobStatus, string> = {
  new: "New",
  interested: "Interested",
  applied: "Applied",
  interviewing: "Interviewing",
  offer: "Offer",
  rejected: "Rejected",
  not_for_me: "Not for me",
};

export const PRIORITY_LABELS: Record<number, string> = { 1: "P1 Dream", 2: "P2 Strong", 3: "P3 Good" };

export const SOURCE_KIND: Record<string, string> = {
  html_links: "Web page",
  sitemap: "Sitemap",
  google: "Web page",
  playwright: "Browser",
  manual: "Manual",
  unknown: "Manual",
};
export function sourceKind(sourceType: string): string {
  return SOURCE_KIND[sourceType] ?? "API";
}
