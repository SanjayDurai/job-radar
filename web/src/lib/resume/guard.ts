// Truth guard: turns the LLM's suggestion into a resume that only contains facts from the master.
// Every rule here is deterministic, so a model mistake can't put something untrue on your resume:
//   - bullets must come from a real master bullet (by id) and keep exactly its numbers
//   - nothing from the "gaps" list (job keywords you don't have) may appear unless it was already there
//   - skills must exist in the master; the role title and years of experience never change
// When a suggestion breaks a rule, the original master wording is used instead.

import { CATEGORY_WORDS, dedupe, hasKeyword, normalize, sameKeyword, supportedBy } from "./score";
import type { Change, Keywords, MasterResume, SkillGroup, TailoredBullet, TailoredResume } from "./types";

export type RawTailored = {
  headline_skills?: string[];
  summary?: string;
  skills?: Record<string, string[]>;
  experience?: { id: string; bullets?: { source_id: string; text: string }[] }[];
  projects?: { id: string; bullets?: { source_id: string; text: string }[] }[];
};

const MAX_BULLETS_FIRST_ROLE = 5;
const MAX_BULLETS_OTHER_ROLES = 2;
const MAX_PROJECTS = 3;
const MAX_PROJECT_BULLETS = 2;

// Compare the numbers themselves ("60%", "60 %" and "60" are the same number), not their formatting
const numbers = (s: string) => new Set((s.replace(/\*\*/g, "").match(/\d+(?:[.,]\d+)?/g) ?? []).map((n) => String(Number(n.replace(",", ".")))));
const plain = (s: string) => s.replace(/\*\*/g, "").replace(/\s+/g, " ").trim();
const YEARS = /(\d+)\s*\+?\s*years?/gi;

export function masterText(m: MasterResume): string {
  return [
    m.basics.headline,
    m.summary,
    ...m.skills.flatMap((g) => g.items),
    ...m.experience.flatMap((e) => [e.title, e.subtitle, ...e.bullets.map((b) => b.text)]),
    ...(m.projects ?? []).flatMap((p) => [p.name, ...(p.tech ?? []), ...p.bullets.map((b) => b.text)]),
    ...(m.certifications?.items ?? []),
  ]
    .filter(Boolean)
    .join("\n");
}

// Named technologies in a bullet are evidence for a recruiter: a rewrite may not silently drop them.
const TECH_IN_BULLETS = [
  "Greenhouse", "Lever", "Workday", "Playwright", "GitHub Actions", "LangGraph", "LangChain", "AWS Lambda", "SQL",
  "Python", "Java", "Spring Boot", "OpenCV", "Tesseract", "RAG", "YOLOv5s", "WhatsApp", "Next.js", "PostgreSQL", "FAISS",
];

/** Why a rewritten line isn't allowed, or null if it's fine. `tech` = named technologies to keep. */
export function bulletProblem(source: string, candidate: string, gaps: string[], tech: string[] = TECH_IN_BULLETS): string | null {
  const c = plain(candidate);
  if (!c) return "empty";
  const src = numbers(source);
  const cand = numbers(candidate);
  for (const n of cand) if (!src.has(n)) return `adds a number not in the original (${n})`;
  for (const n of src) if (!cand.has(n)) return `drops a number from the original (${n})`;
  for (const g of gaps) if (hasKeyword(c, g) && !hasKeyword(source, g)) return `claims "${g}", which isn't in your master resume`;
  for (const t of tech) if (hasKeyword(source, t) && !hasKeyword(c, t)) return `drops "${t}" from the original`;
  if (c.length > Math.max(plain(source).length * 1.6, plain(source).length + 90)) return "much longer than the original";
  return null;
}

function summaryProblem(m: MasterResume, candidate: string, gaps: string[]): string | null {
  const c = plain(candidate);
  if (!c || c.length > 520) return "missing or too long";
  const allowedYears = new Set([...(m.summary ?? "").matchAll(YEARS)].map((x) => x[1]));
  for (const y of c.matchAll(YEARS)) if (!allowedYears.has(y[1])) return `changes years of experience (${y[0]})`;
  const all = numbers(masterText(m));
  for (const n of numbers(c)) if (!all.has(n)) return `adds a number not in your resume (${n})`;
  for (const g of gaps) if (hasKeyword(c, g) && !hasKeyword(m.summary ?? "", g)) return `claims "${g}"`;
  return null;
}

/** "60 % to 85 %" -> "60% to 85%", tidy spaces. */
export function tidy(text: string): string {
  return text.replace(/(\d)\s+%/g, "$1%").replace(/\s+([,.;:])/g, "$1").replace(/\s{2,}/g, " ").trim();
}

/**
 * A rewrite may bring in a skill only if that same job/project entry already shows it (so "SQL" can't
 * hop from your TCS role into a project that never used SQL). Category words ("databases", "cloud")
 * are fine when that entry has a specific skill implying them.
 */
export function contextProblem(source: string, candidate: string, entryContext: string, skills: string[]): string | null {
  for (const t of [...skills, ...CATEGORY_WORDS]) {
    if (hasKeyword(candidate, t) && !hasKeyword(source, t) && !supportedBy(entryContext, t))
      return `brings in "${t}" from a different part of your resume`;
  }
  return null;
}

function pickBullets(
  sources: { id: string; text: string }[],
  suggested: { source_id: string; text: string }[] | undefined,
  max: number,
  gaps: string[],
  section: string,
  changes: Change[],
  notes: string[],
  entryContext: string,
  skills: string[],
): TailoredBullet[] {
  const byId = new Map(sources.map((b) => [b.id, b]));
  const out: TailoredBullet[] = [];
  for (const s of suggested ?? []) {
    const src = byId.get(s.source_id);
    if (!src || out.some((o) => o.sourceId === src.id)) continue; // unknown or repeated source: ignore
    const candidate = tidy(s.text ?? "");
    const problem = bulletProblem(src.text, candidate, gaps) ?? contextProblem(src.text, candidate, entryContext, skills);
    if (problem) notes.push(`Kept the original wording for one ${section} bullet: the rewrite ${problem}.`);
    const text = problem ? src.text : candidate;
    if (plain(text) !== plain(src.text)) changes.push({ section, before: src.text, after: text });
    out.push({ sourceId: src.id, text });
    if (out.length >= max) break;
  }
  if (!out.length) return sources.slice(0, max).map((b) => ({ sourceId: b.id, text: b.text }));
  return out;
}

export function applyGuard(
  m: MasterResume,
  raw: RawTailored,
  gaps: string[],
): { resume: TailoredResume; changes: Change[]; notes: string[] } {
  const changes: Change[] = [];
  const notes: string[] = [];

  // Headline: keep the role ("AI Engineer"); reorder/choose the skills after it, but only true ones
  const role = (m.basics.headline ?? "").split(/\s+[–-]\s+/)[0];
  const truth = masterText(m);
  const headSkills = dedupe((raw.headline_skills ?? []).filter((s) => hasKeyword(truth, s) && !gaps.some((g) => sameKeyword(g, s)))).slice(0, 6);
  const headline = headSkills.length >= 3 ? `${role} – ${headSkills.join(" · ")}` : m.basics.headline;
  if (headline !== m.basics.headline) changes.push({ section: "Headline", before: m.basics.headline ?? "", after: headline ?? "" });

  // Summary
  let summary = m.summary;
  if (raw.summary) {
    const problem = summaryProblem(m, raw.summary, gaps);
    if (problem) notes.push(`Kept your original summary: the rewrite ${problem}.`);
    else if (plain(raw.summary) !== plain(m.summary ?? "")) {
      summary = tidy(raw.summary);
      changes.push({ section: "Summary", before: m.summary ?? "", after: summary });
    }
  }

  // Skills: every master skill stays (more true keywords = more ATS hits); the LLM only decides the
  // order: groups it lists first come first, and its picks lead each group.
  const suggested = Object.values(raw.skills ?? {}).flat();
  const groupRank = (g: string) => {
    const i = Object.keys(raw.skills ?? {}).findIndex((k) => normalize(k) === normalize(g));
    return i === -1 ? 99 : i;
  };
  const skills: SkillGroup[] = m.skills
    .map(({ group, items }, i) => {
      const picked = dedupe(suggested.map((s) => items.find((l) => sameKeyword(l, s) || normalize(l) === normalize(s))).filter(Boolean) as string[]);
      return { group, items: [...picked, ...items.filter((x) => !picked.includes(x))], rank: groupRank(group) * 100 + i };
    })
    .sort((a, b) => a.rank - b.rank)
    .map(({ group, items }) => ({ group, items }));

  const allSkills = m.skills.flatMap((g) => g.items);

  // Experience: chronological order kept; bullets chosen + reworded from that role's own bullets
  const experience = m.experience.map((e, i) => {
    const sug = raw.experience?.find((x) => x.id === e.id)?.bullets;
    const max = i === 0 ? MAX_BULLETS_FIRST_ROLE : MAX_BULLETS_OTHER_ROLES;
    const { bullets, ...rest } = e;
    const context = [e.title, e.subtitle, ...bullets.map((b) => b.text)].join("\n");
    return { ...rest, bullets: pickBullets(bullets, sug, max, gaps, `${e.company} experience`, changes, notes, context, allSkills) };
  });

  // Projects: most relevant first (LLM order), at most 3
  const masterProjects = m.projects ?? [];
  const order = (raw.projects ?? []).map((p) => p.id).filter((id) => masterProjects.some((p) => p.id === id));
  const chosenIds = (order.length ? dedupe(order) : masterProjects.map((p) => p.id)).slice(0, MAX_PROJECTS);
  const projects = chosenIds.map((id) => {
    const p = masterProjects.find((x) => x.id === id)!;
    const sug = raw.projects?.find((x) => x.id === id)?.bullets;
    const { bullets, ...rest } = p;
    const context = [p.name, ...(p.tech ?? []), ...bullets.map((b) => b.text)].join("\n");
    return { ...rest, bullets: pickBullets(bullets, sug, MAX_PROJECT_BULLETS, gaps, `${p.name} project`, changes, notes, context, allSkills) };
  });

  return {
    resume: { ...m, basics: { ...m.basics, headline }, summary, skills, experience, projects },
    changes,
    notes,
  };
}

/** Move skills that the job asks for to the front of their group (recruiters skim left to right). */
export function prioritizeJobSkills(r: TailoredResume, kw: Keywords): string[] {
  const wanted = [...kw.mustHave, ...kw.niceToHave];
  const moved: string[] = [];
  for (const g of r.skills) {
    const hits = g.items.filter((s) => wanted.some((k) => sameKeyword(s, k)));
    g.items = [...hits, ...g.items.filter((s) => !hits.includes(s))];
    moved.push(...hits);
  }
  return moved;
}

/** Split job keywords into ones your master resume supports and ones it doesn't (gaps). */
// "LLM-based systems" -> "LLM", "CI/CD pipelines" -> "CI/CD": a generic ending around a real skill
const GENERIC_ENDING = /(?:[-\s](?:based|powered|driven|enabled))?\s+(?:systems?|pipelines?|applications?|apps?|solutions?|development|workflows?|models?|services?|tools?|tooling|platforms?|products?|engineering)$/i;

export function splitSupported(m: MasterResume, kw: Keywords): { supported: string[]; gaps: string[] } {
  const truth = masterText(m);
  const skills = m.skills.flatMap((g) => g.items);
  const isTrue = (k: string) => {
    if (supportedBy(truth, k)) return true;
    const core = k.replace(GENERIC_ENDING, "").trim();
    // only when what's left is one of YOUR skills (so "data platforms" or "Azure Functions" don't count)
    return core !== k && core.length > 1 && (skills.some((s) => sameKeyword(s, core)) || CATEGORY_WORDS.includes(normalize(core).trim())) && supportedBy(truth, core);
  };
  const all = dedupe([...kw.mustHave, ...kw.niceToHave]);
  return { supported: all.filter(isTrue), gaps: all.filter((k) => !isTrue(k)) };
}
