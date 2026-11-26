// Keyword matching and the ATS-style score. Pure functions: no network, easy to test.
//
// Score (0-100) = 85% keyword coverage + 15% format checks.
//   keyword coverage = (2 × must-have matched + 1 × nice-to-have matched) / (2 × must-have + nice-to-have)
// It is our own transparent score (ATS products don't publish theirs), built on what they all reward:
// the job's own keywords, spelled the way the job spells them, in a plain parseable layout.

import type { Check, Keywords, MasterResume, TailoredResume } from "./types";

// Spellings that mean the same thing. Matching any variant counts as a match.
const SYNONYMS: string[][] = [
  ["llm", "llms", "large language model", "large language models"],
  ["genai", "gen ai", "generative ai"],
  ["agentic ai", "agentic", "ai agents", "ai agent", "agents"],
  ["rag", "retrieval augmented generation"],
  ["aws", "amazon web services"],
  ["machine learning", "ml"],
  ["deep learning"],
  ["nlp", "natural language processing"],
  ["computer vision", "cv"],
  ["rest api", "rest apis", "restful", "restful apis"],
  ["javascript", "js"],
  ["typescript"],
  ["kubernetes", "k8s"],
  ["ci cd", "cicd", "ci/cd"],
  ["postgresql", "postgres"],
  ["gcp", "google cloud", "google cloud platform"],
  ["azure", "microsoft azure", "azure ai"],
  ["prompt engineering", "prompting", "prompt design"],
  ["scikit learn", "sklearn"],
  ["git", "github"],
  ["ai", "artificial intelligence"],
  ["vector database", "vector databases", "vector db", "faiss"],
];

// Category words a job uses that a specific skill truthfully implies ("databases" ← PostgreSQL).
// Used only to decide what you may claim, never to fake a match: the tailored resume must still
// contain the job's actual word for the score to count it. Keep this list conservative.
const IMPLIED_BY: [string[], string[]][] = [
  [["databases", "database", "relational databases", "rdbms", "sql databases"], ["postgresql", "sql", "mysql", "oracle"]],
  [["cloud", "cloud platforms", "cloud platform", "cloud services", "cloud computing", "public cloud"], ["aws", "azure", "gcp"]],
  [["serverless"], ["aws lambda"]],
  [["agentic workflows", "agent workflows", "ai workflows", "llm agents", "agent orchestration"], ["agentic ai", "ai agents", "langgraph"]],
  [["vector retrieval", "vector search", "semantic search", "embeddings"], ["faiss", "rag"]],
  [["llm orchestration", "llm frameworks"], ["langchain", "langgraph"]],
  [["containerization", "containers"], ["docker"]],
  [["version control"], ["git", "github"]],
  [["backend", "backend development", "apis"], ["fastapi", "rest apis", "spring boot", "node.js"]],
  [["ci/cd"], ["github actions"]],
];

/** Category words from the table above (e.g. "databases", "cloud platforms"). */
export const CATEGORY_WORDS: string[] = IMPLIED_BY.flatMap(([cats]) => cats);

/** Is the job keyword true for you: in your master, or implied by a specific skill you list? */
export function supportedBy(truth: string, keyword: string): boolean {
  if (hasKeyword(truth, keyword)) return true;
  const k = normalize(keyword).trim();
  return IMPLIED_BY.some(([cats, specifics]) => cats.includes(k) && specifics.some((s) => hasKeyword(truth, s)));
}

export function normalize(s: string): string {
  return ` ${s
    .toLowerCase()
    .replace(/\*\*/g, "")
    .replace(/[^a-z0-9+#./]+/g, " ")
    .replace(/(\w)[./](\s|$)/g, "$1$2") // trailing dots/slashes ("Python." -> "python")
    .replace(/\s+/g, " ")
    .trim()} `;
}

function variants(keyword: string): string[] {
  const k = normalize(keyword).trim();
  const group = SYNONYMS.find((g) => g.some((v) => normalize(v).trim() === k));
  return group ? group.map((v) => normalize(v).trim()) : [k];
}

/** Is the keyword (or a synonym) in the text, as whole words? */
export function hasKeyword(text: string, keyword: string): boolean {
  const hay = normalize(text);
  return variants(keyword).some((v) => v && hay.includes(` ${v} `));
}

// --- resume -> plain text (what an ATS "sees") -----------------------------------------------------

export function resumeText(r: MasterResume | TailoredResume): string {
  const parts: string[] = [r.basics.name, r.basics.headline ?? "", r.summary ?? ""];
  for (const { group, items } of r.skills) parts.push(`${group}: ${items.join(", ")}`);
  for (const e of r.experience) {
    parts.push(`${e.title} ${e.company} ${e.subtitle ?? ""}`);
    for (const b of e.bullets) parts.push(b.text);
  }
  for (const p of r.projects ?? []) {
    parts.push(`${p.name} ${(p.tech ?? []).join(", ")}`);
    for (const b of p.bullets) parts.push(b.text);
  }
  for (const ed of r.education ?? []) parts.push(`${ed.degree} ${ed.school}`);
  parts.push(...(r.certifications?.items ?? []));
  return parts.join("\n");
}

export function wordCount(r: MasterResume | TailoredResume): number {
  return resumeText(r).split(/\s+/).filter(Boolean).length;
}

// --- format checks (things ATS parsers trip over) -----------------------------------------------

export function formatChecks(r: MasterResume | TailoredResume): Check[] {
  const words = wordCount(r);
  const bullets: { text: string }[] = [
    ...r.experience.flatMap((e): { text: string }[] => e.bullets),
    ...(r.projects ?? []).flatMap((p): { text: string }[] => p.bullets),
  ];
  return [
    { label: "Standard section headings (Summary, Skills, Experience, Projects, Education)", ok: true },
    { label: "Single column, no tables, text boxes or images", ok: true },
    { label: "Email and phone in plain text", ok: Boolean(r.basics.email && r.basics.phone) },
    { label: "Every role has dates", ok: r.experience.every((e) => Boolean(e.dates)) },
    { label: "Skills section present", ok: r.skills.some((g) => g.items.length > 0) },
    {
      label: "Fits one page (about 300–650 words)",
      ok: words >= 300 && words <= 650,
      detail: `${words} words`,
    },
    {
      label: "Bullets are one or two lines",
      ok: bullets.every((b) => b.text.replace(/\*\*/g, "").length <= 230),
    },
  ];
}

// --- the score -------------------------------------------------------------------------------------

export type ScoreResult = {
  score: number;
  keywordScore: number;
  formatScore: number;
  matched: string[];
  unmatched: string[];
  checks: Check[];
};

export function scoreResume(r: MasterResume | TailoredResume, kw: Keywords, text = resumeText(r)): ScoreResult {
  const must = dedupe(kw.mustHave);
  const nice = dedupe(kw.niceToHave).filter((k) => !must.some((m) => sameKeyword(m, k)));
  const matched: string[] = [];
  const unmatched: string[] = [];
  let got = 0;
  for (const [list, weight] of [[must, 2], [nice, 1]] as const) {
    for (const k of list) {
      if (hasKeyword(text, k)) {
        matched.push(k);
        got += weight;
      } else unmatched.push(k);
    }
  }
  const total = must.length * 2 + nice.length;
  const keywordScore = total ? Math.round((got / total) * 100) : 100;
  const checks = formatChecks(r);
  const formatScore = Math.round((checks.filter((c) => c.ok).length / checks.length) * 100);
  return {
    score: Math.round(keywordScore * 0.85 + formatScore * 0.15),
    keywordScore,
    formatScore,
    matched,
    unmatched,
    checks,
  };
}

export function sameKeyword(a: string, b: string): boolean {
  const va = variants(a);
  return variants(b).some((v) => va.includes(v));
}

export function dedupe(list: string[]): string[] {
  const out: string[] = [];
  for (const k of list.map((x) => x.trim()).filter(Boolean)) if (!out.some((o) => sameKeyword(o, k))) out.push(k);
  return out;
}
