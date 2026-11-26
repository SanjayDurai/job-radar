// Shape of resume/master.yaml (uploaded to app_state 'resume_master' by `radar resume-upload`).

export type Link = { label: string; url: string };
export type SkillGroup = { group: string; items: string[] };
export type Bullet = { id: string; text: string };

export type MasterResume = {
  basics: { name: string; headline?: string; phone?: string; location?: string; email: string; links?: Link[] };
  summary?: string;
  skills: SkillGroup[]; // ordered (stored as a list: JSONB would reorder object keys)
  experience: { id: string; title: string; company: string; dates?: string; subtitle?: string; bullets: Bullet[] }[];
  projects?: { id: string; name: string; tech?: string[]; link?: Link; bullets: Bullet[] }[];
  education?: { degree: string; school: string; dates?: string }[];
  certifications?: { items: string[]; link?: Link };
};

/** A tailored resume: same shape as the master, bullets keep the id of the master bullet they came from. */
export type TailoredBullet = { sourceId: string; text: string };
export type TailoredResume = Omit<MasterResume, "experience" | "projects"> & {
  experience: (Omit<MasterResume["experience"][number], "bullets"> & { bullets: TailoredBullet[] })[];
  projects: (Omit<NonNullable<MasterResume["projects"]>[number], "bullets"> & { bullets: TailoredBullet[] })[];
};

export type Keywords = { roleTitle: string; mustHave: string[]; niceToHave: string[] };

export type Check = { label: string; ok: boolean; detail?: string };

export type Change = { section: string; before: string; after: string };

export type TailorReport = {
  matched: string[];
  missing: string[]; // in the job description AND in your master resume, but not on this version
  gaps: string[]; // in the job description, NOT in your master resume: never added
  checks: Check[];
  changes: Change[];
  keywordScore: number;
  formatScore: number;
  pdfReadable: boolean | null;
  pages: number | null;
  notes: string[];
};
