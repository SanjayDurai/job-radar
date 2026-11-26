import { describe, expect, it } from "vitest";

import { applyGuard, bulletProblem, contextProblem, prioritizeJobSkills, splitSupported, tidy } from "./guard";
import { hasKeyword, normalize, scoreResume } from "./score";
import type { Keywords, MasterResume } from "./types";

const master: MasterResume = {
  basics: { name: "Test Person", headline: "AI Engineer – LLMs · RAG · Python", phone: "+91 1", email: "t@example.com" },
  summary: "AI Automation Engineer with 1+ year building Generative AI systems in Python.",
  skills: [
    { group: "GenAI & Agents", items: ["LLMs", "RAG", "LangGraph", "Prompt Engineering"] },
    { group: "Languages & Backend", items: ["Python", "SQL", "FastAPI"] },
    { group: "Cloud & Tools", items: ["AWS Lambda", "Docker"] },
  ],
  experience: [
    {
      id: "tcs",
      title: "Systems Engineer",
      company: "TCS",
      dates: "Aug 2025 – Present",
      bullets: [
        { id: "a", text: "Built an agentic route-planning assistant that cut planning from 1 hr to 2 min." },
        { id: "b", text: "Developed a multi-tool LLM agent (LangGraph) on AWS Lambda and SQL." },
        { id: "c", text: "Raised truck load utilization from 60% to 85%." },
      ],
    },
  ],
  projects: [
    { id: "p1", name: "ZivaDesk", tech: ["Python"], bullets: [{ id: "p1a", text: "Launched a multi-tenant SaaS with RAG." }] },
    { id: "p2", name: "Sign detection", tech: ["OpenCV"], bullets: [{ id: "p2a", text: "Trained YOLOv5s at 87% accuracy." }] },
  ],
  education: [{ degree: "B.Tech", school: "VIT", dates: "2021 – 2025" }],
};

const kw: Keywords = { roleTitle: "ML Engineer", mustHave: ["Python", "LLM", "RAG", "Kubernetes"], niceToHave: ["Docker", "FastAPI"] };

describe("keyword matching", () => {
  it("matches whole words and synonyms", () => {
    expect(hasKeyword("Built LLMs with Python.", "LLM")).toBe(true);
    expect(hasKeyword("Generative AI pipelines", "GenAI")).toBe(true);
    expect(hasKeyword("Amazon Web Services", "AWS")).toBe(true);
    expect(hasKeyword("pythonic code", "Python")).toBe(false);
    expect(hasKeyword("**RAG** pipelines", "RAG")).toBe(true);
  });
  it("normalizes punctuation", () => {
    expect(normalize("Node.js, CI/CD!")).toContain("node.js");
  });
});

describe("score", () => {
  it("weights must-haves double and reports what's matched", () => {
    const s = scoreResume(master, kw);
    expect(s.matched).toEqual(expect.arrayContaining(["Python", "LLM", "RAG", "Docker", "FastAPI"]));
    expect(s.unmatched).toEqual(["Kubernetes"]);
    // (2+2+2+0 + 1+1) / (8+2) = 80% keyword coverage
    expect(s.keywordScore).toBe(80);
  });
});

describe("truth guard", () => {
  const { gaps } = splitSupported(master, kw);

  it("knows which job keywords you don't have", () => {
    expect(gaps).toEqual(["Kubernetes"]);
  });

  it("rejects invented or dropped numbers and claimed gaps", () => {
    const src = "Raised truck load utilization from 60% to 85%.";
    expect(bulletProblem(src, "Raised **load utilization** from 60% to 85% using ML.", gaps)).toBeNull();
    expect(bulletProblem(src, "Raised utilization from 60% to 95%.", gaps)).toMatch(/adds a number/);
    expect(bulletProblem(src, "Raised truck load utilization.", gaps)).toMatch(/drops a number/);
    expect(bulletProblem(src, "Raised utilization from 60% to 85% on Kubernetes.", gaps)).toMatch(/Kubernetes/);
  });

  it("compares numbers, not their formatting", () => {
    const src = "Raised truck load utilization from 60% to 85%.";
    expect(bulletProblem(src, "Raised **truck load utilization** 60 % → 85 %.", gaps)).toBeNull();
    expect(bulletProblem("Cut planning from 1 hr to 2 min.", "Cut planning time from 1 hour to 2 minutes.", gaps)).toBeNull();
  });

  it("treats category words as true when a specific skill implies them", () => {
    const { supported, gaps: g } = splitSupported(master, {
      roleTitle: "x",
      mustHave: ["databases", "cloud platforms", "agentic workflows", "function calling"],
      niceToHave: [],
    });
    expect(supported).toEqual(["databases", "cloud platforms", "agentic workflows"]); // SQL, AWS Lambda, LangGraph
    expect(g).toEqual(["function calling"]); // not implied by anything: stays a gap
  });

  it("sees through generic endings only when the core is a real skill", () => {
    const { supported, gaps: g } = splitSupported(master, {
      roleTitle: "x",
      mustHave: ["LLM-based systems", "RAG pipelines", "Azure Functions", "data platforms", "vector retrieval"],
      niceToHave: [],
    });
    expect(supported).toEqual(["LLM-based systems", "RAG pipelines", "vector retrieval"]); // RAG implies vector retrieval
    expect(g).toEqual(["Azure Functions", "data platforms"]);
  });

  it("uses the original wording when a rewrite breaks a rule, and ignores made-up bullets", () => {
    const { resume, notes, changes } = applyGuard(
      master,
      {
        summary: "AI Engineer with 3+ years of experience in LLMs.", // changes years: rejected
        experience: [
          {
            id: "tcs",
            bullets: [
              { source_id: "b", text: "Developed a multi-tool **LLM** agent (LangGraph) on AWS Lambda and SQL for routing." },
              { source_id: "c", text: "Raised utilization from 60% to 99%." }, // invented number: original kept
              { source_id: "zzz", text: "Led a team of 10 engineers." }, // no such source bullet: dropped
            ],
          },
        ],
        projects: [{ id: "p2", bullets: [] }, { id: "nope", bullets: [] }],
        skills: { any: ["Docker", "Kubernetes", "Python"] },
      },
      gaps,
    );
    expect(resume.summary).toBe(master.summary);
    expect(resume.experience[0].bullets.map((b) => b.sourceId)).toEqual(["b", "c"]);
    expect(resume.experience[0].bullets[1].text).toBe("Raised truck load utilization from 60% to 85%.");
    expect(resume.projects.map((p) => p.id)).toEqual(["p2"]);
    expect(resume.skills.flatMap((g) => g.items)).not.toContain("Kubernetes");
    expect(notes.join(" ")).toMatch(/years of experience/);
    expect(changes.some((c) => c.after.includes("routing"))).toBe(true);
  });

  it("keeps every master skill, in the order the rewrite suggests, job skills first", () => {
    const { resume } = applyGuard(master, { skills: { "Cloud & Tools": ["Docker"], "GenAI & Agents": ["RAG"] } }, gaps);
    expect(resume.skills.map((g) => g.group)).toEqual(["Cloud & Tools", "GenAI & Agents", "Languages & Backend"]);
    expect(resume.skills.flatMap((g) => g.items).sort()).toEqual(master.skills.flatMap((g) => g.items).sort()); // nothing lost
    expect(resume.skills[1].items[0]).toBe("RAG");
    prioritizeJobSkills(resume, kw);
    expect(resume.skills[2].items.slice(0, 2)).toEqual(["Python", "FastAPI"]); // asked for by the job
  });

  it("won't move a skill into an entry that never used it", () => {
    const skills = master.skills.flatMap((g) => g.items);
    const ziva = "ZivaDesk\nPython\nLaunched a multi-tenant SaaS with RAG.";
    expect(contextProblem("Launched a multi-tenant SaaS with RAG.", "Launched a multi-tenant SaaS with RAG and SQL.", ziva, skills)).toMatch(/SQL/);
    const tcs = "Systems Engineer\nDeveloped a multi-tool LLM agent (LangGraph) on AWS Lambda and SQL.";
    // AWS Lambda is in this role, so "cloud" (implied) and "SQL" (same role) are fine
    expect(contextProblem("Built an agentic assistant.", "Built an agentic assistant with SQL on the cloud.", tcs, skills)).toBeNull();
  });

  it("tidies spacing the model sometimes adds", () => {
    expect(tidy("from 60 % to 85 % , fast")).toBe("from 60% to 85%, fast");
  });

  it("rejects a rewrite that drops a named technology", () => {
    const src = "Tracked 100 companies via ATS APIs (Greenhouse, Lever, Workday) with a Playwright fallback.";
    expect(bulletProblem(src, "Tracked 100 companies via public APIs.", gaps)).toMatch(/drops "Greenhouse"/);
    expect(bulletProblem(src, "Tracked 100 companies via **ATS APIs** (Greenhouse, Lever, Workday) and Playwright.", gaps)).toBeNull();
  });
});
