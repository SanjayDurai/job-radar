import "server-only";

import Groq from "groq-sdk";

import { applyGuard, prioritizeJobSkills, splitSupported, type RawTailored } from "./guard";
import { dedupe, hasKeyword, resumeText, sameKeyword, scoreResume } from "./score";
import type { Change, Keywords, MasterResume, TailoredResume } from "./types";

// gpt-oss models on Groq's free tier: 1,000 requests/day and 8,000 tokens/minute PER MODEL, so the
// small keyword step uses the 20B model and the rewrite uses the 120B model (separate budgets).
const KEYWORD_MODEL = process.env.RESUME_KEYWORD_MODEL ?? "openai/gpt-oss-20b";
const TAILOR_MODEL = process.env.RESUME_TAILOR_MODEL ?? "openai/gpt-oss-120b";
export const TARGET_SCORE = 75;

function groq() {
  const apiKey = process.env.GROQ_API_KEY;
  if (!apiKey) throw new Error("GROQ_API_KEY isn't set on the server, so resumes can't be tailored yet.");
  return new Groq({ apiKey, maxRetries: 3, timeout: 60_000 });
}

async function json<T>(model: string, system: string, user: string, maxTokens: number): Promise<T> {
  const res = await groq().chat.completions.create({
    model,
    temperature: 0,
    reasoning_effort: "low",
    max_completion_tokens: maxTokens,
    response_format: { type: "json_object" },
    messages: [
      { role: "system", content: system },
      { role: "user", content: user },
    ],
  });
  const text = res.choices[0]?.message?.content ?? "";
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error("The AI returned something that wasn't valid JSON. Try again.");
  }
}

const strList = (v: unknown, max: number) =>
  Array.isArray(v) ? dedupe(v.filter((x): x is string => typeof x === "string" && x.trim().length > 1 && x.length < 60)).slice(0, max) : [];

// Words that show up in job ads but are never ATS skill keywords (a backstop for the model)
const NOT_A_SKILL =
  /\b(publications?|papers?|journals?|conferences?|partners?|marketplace|sellers?|customers?|toolkits?|self[- ]developed|state of the art|state-of-the-art|personali[sz]ed|impact|leadership|stakeholders?|ownership|mission|culture|research|innovation|excellence|best practices|world[- ]class|scalable|large[- ]scale|productioni[sz]ing|end[- ]to[- ]end|code)\b/i;

export async function extractKeywords(job: { title: string; company: string; description: string }): Promise<Keywords> {
  const raw = await json<{ role_title?: string; must_have?: unknown; nice_to_have?: unknown }>(
    KEYWORD_MODEL,
    `You pick the keywords an applicant tracking system (ATS) filters resumes on for this job.
Return JSON: {"role_title": string, "must_have": [string], "nice_to_have": [string]}.

Include ONLY things a candidate would list in a resume's Skills section:
programming languages, frameworks, libraries, tools, platforms, databases, cloud services,
AI/ML techniques and model types (e.g. "Reinforcement Learning", "LLMs", "RAG", "Computer Vision"),
engineering practices (e.g. "CI/CD", "Microservices", "A/B testing"), and named fields such as "Statistics".

EXCLUDE: business or domain phrases ("selling partners", "marketplace", "supply chain"), research or
publication expectations ("white papers", "top-tier publications"), generic words ("toolkits",
"self-developed code", "state of the art", "personalized", "research", "scalable", "productionizing"),
soft skills, years of experience, degrees, benefits, locations, team names and the company name.

- must_have: up to 12, from required/basic qualifications and core responsibilities.
- nice_to_have: up to 8, from preferred qualifications ("a plus", "bonus").
- Use the posting's spelling. If it gives both a full name and an abbreviation ("Reinforcement Learning (RL)"), use the full name.
- 1-3 words each. No duplicates.`,
    `Title: ${job.title}
Company: ${job.company}

${job.description.slice(0, 7000)}`,
    1200,
  );
  const companyWords = job.company.toLowerCase().split(/\W+/).filter((w) => w.length > 2);
  const clean = (v: unknown, max: number) =>
    strList(v, 30)
      .filter((k) => k.split(/\s+/).length <= 3 && !NOT_A_SKILL.test(k))
      .filter((k) => !companyWords.some((w) => k.toLowerCase().includes(w)))
      .slice(0, max);
  const mustHave = clean(raw.must_have, 12);
  return {
    roleTitle: String(raw.role_title ?? job.title).slice(0, 120),
    mustHave,
    niceToHave: clean(raw.nice_to_have, 8).filter((k) => !mustHave.some((m) => sameKeyword(m, k))),
  };
}

function masterForPrompt(m: MasterResume) {
  return {
    headline: m.basics.headline,
    summary: m.summary,
    skills: Object.fromEntries(m.skills.map((g) => [g.group, g.items])),
    experience: m.experience.map((e) => ({ id: e.id, title: e.title, company: e.company, bullets: e.bullets })),
    projects: (m.projects ?? []).map((p) => ({ id: p.id, name: p.name, tech: p.tech, bullets: p.bullets })),
  };
}

const TAILOR_RULES = `You tailor a resume to a job posting. You may ONLY rephrase, reorder, select and emphasize facts that
are already in the master resume. Never add an employer, title, tool, skill, metric, number or claim that isn't there.

Return JSON:
{"headline_skills": [3-6 skills from the master, most relevant first],
 "summary": "2-3 sentences, true to the master summary, using the job's own wording where it is truthful. Keep its strongest achievement with its numbers and every venture or product it names.",
 "skills": {"<master group name>": [skills from that group, most relevant first]} (list the most relevant group first),
 "experience": [{"id": "<master experience id>", "bullets": [{"source_id": "<master bullet id>", "text": "rewritten bullet"}]}],
 "projects": [{"id": "<master project id>", "bullets": [{"source_id": "...", "text": "..."}]}]}

Rules:
- Every bullet must have the source_id of the master bullet it rewrites, and keep EVERY number from it exactly.
- Keep every named technology, tool and platform a bullet mentions (e.g. "Greenhouse, Lever, Workday", "Playwright").
  You may add the job's wording, never remove specifics.
- Use the posting's exact spelling for keywords you can truthfully use ("LLMs", "Generative AI", "CI/CD").
- Do not mention anything from the "do not claim" list.
- Experience: keep all roles; up to 5 bullets for the current role and 2 for others, most relevant first.
- Projects: the 3 most relevant, most relevant first, up to 2 bullets each.
- Wrap 2-4 key terms per bullet in **double asterisks** for bold.
- Keep the total to one page: each bullet under 220 characters.
- Keep the years of experience exactly as the master states them.`;

export type TailorOutcome = {
  resume: TailoredResume;
  keywords: Keywords;
  scoreBefore: number;
  scoreAfter: number;
  matched: string[];
  missing: string[];
  gaps: string[];
  changes: Change[];
  notes: string[];
  keywordScore: number;
  formatScore: number;
  checks: ReturnType<typeof scoreResume>["checks"];
  model: string;
};

export async function tailorResume(master: MasterResume, job: { title: string; company: string; description: string }): Promise<TailorOutcome> {
  const keywords = await extractKeywords(job);
  if (keywords.mustHave.length + keywords.niceToHave.length === 0) throw new Error("Couldn't find any skills or tools in this job description.");
  const { supported, gaps } = splitSupported(master, keywords);
  const before = scoreResume(master, keywords);

  const prompt = (extra = "") =>
    `JOB: ${job.title} at ${job.company}
Keywords to use where truthful: ${JSON.stringify(supported)}
Do not claim (not in the master resume): ${JSON.stringify(gaps)}
${extra}
MASTER RESUME (JSON):
${JSON.stringify(masterForPrompt(master))}

JOB DESCRIPTION:
${job.description.slice(0, 5000)}`;

  let raw = await json<RawTailored>(TAILOR_MODEL, TAILOR_RULES, prompt(), 3500);
  let { resume, changes, notes } = applyGuard(master, raw, gaps);
  prioritizeJobSkills(resume, keywords);
  let after = scoreResume(resume, keywords);

  // One more pass if supported keywords are still missing and we're under the target
  const stillMissing = () => supported.filter((k) => !hasKeyword(resumeText(resume), k));
  if (after.score < TARGET_SCORE && stillMissing().length) {
    raw = await json<RawTailored>(
      TAILOR_MODEL,
      TAILOR_RULES,
      prompt(`These keywords are true for the candidate (they appear in the master) but are missing from your last version. Work each one into the bullet or summary where the master already supports it: ${JSON.stringify(stillMissing())}`),
      3500,
    );
    const second = applyGuard(master, raw, gaps);
    prioritizeJobSkills(second.resume, keywords);
    const secondScore = scoreResume(second.resume, keywords);
    if (secondScore.score > after.score) {
      ({ resume, changes, notes } = second);
      after = secondScore;
    }
  }

  if (gaps.length) notes.push(`Not added because they aren't in your master resume: ${gaps.join(", ")}. If any are true, add them to resume/master.yaml.`);
  if (after.score < TARGET_SCORE)
    notes.push(`Below ${TARGET_SCORE} because this job asks for things you don't have yet (see gaps). Adding fake keywords would hurt you in interviews.`);

  return {
    resume,
    keywords,
    scoreBefore: before.score,
    scoreAfter: after.score,
    matched: after.matched,
    missing: stillMissing(),
    gaps,
    changes,
    notes,
    keywordScore: after.keywordScore,
    formatScore: after.formatScore,
    checks: after.checks,
    model: TAILOR_MODEL,
  };
}
