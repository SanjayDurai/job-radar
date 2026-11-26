import "server-only";

import {
  AlignmentType,
  BorderStyle,
  Document,
  ExternalHyperlink,
  Packer,
  Paragraph,
  TabStopType,
  TextRun,
  type ParagraphChild,
} from "docx";

import type { TailoredResume } from "./types";

// Word version: the format ATS systems parse most reliably. Same plain single-column layout as the PDF.
const FONT = "Times New Roman";
const SIZE = 20; // half-points: 10 pt
const RIGHT_TAB = 10_430; // A4 width minus 0.5" margins, in twips

const run = (text: string, opts: { bold?: boolean; italics?: boolean; size?: number } = {}) =>
  new TextRun({ text, font: FONT, size: opts.size ?? SIZE, bold: opts.bold, italics: opts.italics });

function rich(text: string): TextRun[] {
  return text
    .split(/(\*\*[^*]+\*\*)/g)
    .filter(Boolean)
    .map((p) => (p.startsWith("**") && p.endsWith("**") ? run(p.slice(2, -2), { bold: true }) : run(p)));
}

const link = (label: string, url: string, size = SIZE) =>
  new ExternalHyperlink({ link: url, children: [new TextRun({ text: label, font: FONT, size, color: "1A3DB8" })] });

const heading = (text: string) =>
  new Paragraph({
    spacing: { before: 140, after: 50 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "111111", space: 1 } },
    children: [run(text, { bold: true, size: 21 })],
  });

const bullet = (text: string) =>
  new Paragraph({ spacing: { after: 20 }, indent: { left: 300, hanging: 180 }, children: [run("•\t"), ...rich(text)], tabStops: [{ type: TabStopType.LEFT, position: 300 }] });

const rowWithRight = (left: ParagraphChild[], right: ParagraphChild | string | undefined) =>
  new Paragraph({
    spacing: { before: 60 },
    tabStops: [{ type: TabStopType.RIGHT, position: RIGHT_TAB }],
    children: [...left, ...(right ? [run("\t"), typeof right === "string" ? run(right) : right] : [])],
  });

export async function renderDocx(r: TailoredResume): Promise<Buffer> {
  const [role, ...rest] = (r.basics.headline ?? "").split(/\s+–\s+/);
  const children: Paragraph[] = [
    new Paragraph({ alignment: AlignmentType.CENTER, children: [run(r.basics.name.toUpperCase(), { bold: true, size: 36 })] }),
  ];
  if (r.basics.headline)
    children.push(new Paragraph({ alignment: AlignmentType.CENTER, children: [run(role, { bold: true, size: 21 }), run(rest.length ? ` – ${rest.join(" – ")}` : "", { size: 21 })] }));
  const contact = [r.basics.phone, r.basics.location].filter(Boolean).join("  |  ");
  children.push(
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [run(contact ? `${contact}  |  ` : "", { size: 19 }), link(r.basics.email, `mailto:${r.basics.email}`, 19)],
    }),
  );
  if (r.basics.links?.length)
    children.push(
      new Paragraph({
        alignment: AlignmentType.CENTER,
        children: r.basics.links.flatMap((l, i) => [...(i ? [run("  |  ", { size: 19 })] : []), link(l.label, l.url, 19)]),
      }),
    );

  if (r.summary) children.push(heading("SUMMARY"), new Paragraph({ children: rich(r.summary) }));

  children.push(heading("TECHNICAL SKILLS"));
  for (const { group, items } of r.skills)
    if (items.length) children.push(new Paragraph({ spacing: { after: 20 }, children: [run(`${group}: `, { bold: true }), run(items.join(", "))] }));

  children.push(heading("EXPERIENCE"));
  for (const e of r.experience) {
    children.push(rowWithRight([run(e.title, { bold: true }), run(` – ${e.company}`)], e.dates));
    if (e.subtitle) children.push(new Paragraph({ children: [run(e.subtitle, { italics: true })] }));
    children.push(...e.bullets.map((b) => bullet(b.text)));
  }

  if (r.projects.length) {
    children.push(heading("PROJECTS"));
    for (const p of r.projects) {
      children.push(
        rowWithRight(
          [run(p.name, { bold: true }), ...(p.tech?.length ? [run(` — ${p.tech.join(", ")}`, { italics: true })] : [])],
          p.link ? link(p.link.label, p.link.url) : undefined,
        ),
      );
      children.push(...p.bullets.map((b) => bullet(b.text)));
    }
  }

  if (r.education?.length || r.certifications?.items.length) {
    children.push(heading("EDUCATION & CERTIFICATIONS"));
    for (const ed of r.education ?? []) children.push(rowWithRight([run(ed.degree, { bold: true }), run(` – ${ed.school}`)], ed.dates));
    if (r.certifications?.items.length)
      children.push(
        new Paragraph({
          children: [
            run(r.certifications.items.join("  ·  "), { bold: true }),
            ...(r.certifications.link ? [run("  "), link(`(${r.certifications.link.label})`, r.certifications.link.url)] : []),
          ],
        }),
      );
  }

  const doc = new Document({
    creator: r.basics.name,
    title: `${r.basics.name} - Resume`,
    styles: { default: { document: { run: { font: FONT, size: SIZE } } } },
    sections: [{ properties: { page: { size: { width: 11_906, height: 16_838 }, margin: { top: 600, bottom: 560, left: 720, right: 720 } } }, children }],
  });
  return Packer.toBuffer(doc);
}
