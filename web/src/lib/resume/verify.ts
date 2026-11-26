import "server-only";

import { extractText, getDocumentProxy } from "unpdf";

import { renderPdf } from "./render-pdf";
import { hasKeyword } from "./score";
import type { TailoredResume } from "./types";

/** Read the finished PDF back the way an ATS would: page count + every matched keyword still extractable. */
export async function verifyPdf(r: TailoredResume, matched: string[]): Promise<{ pdf: Buffer; pages: number; readable: boolean; unreadable: string[] }> {
  const pdf = await renderPdf(r);
  const doc = await getDocumentProxy(new Uint8Array(pdf));
  const { totalPages, text } = await extractText(doc, { mergePages: true });
  const unreadable = matched.filter((k) => !hasKeyword(text, k));
  return { pdf, pages: totalPages, readable: unreadable.length === 0, unreadable };
}

/** Keep it to one page: trim the least important content until it fits. */
export async function fitOnePage(r: TailoredResume, matched: string[]) {
  let current = structuredClone(r);
  let result = await verifyPdf(current, matched);
  const trimmed: string[] = [];
  for (let i = 0; i < 6 && result.pages > 1; i++) {
    const lastProject = current.projects.at(-1);
    if (lastProject && lastProject.bullets.length > 1) {
      lastProject.bullets.pop();
      trimmed.push(`a bullet from ${lastProject.name}`);
    } else if (current.projects.length > 2) {
      trimmed.push(`the ${current.projects.pop()!.name} project`);
    } else if (current.experience[0].bullets.length > 3) {
      current.experience[0].bullets.pop();
      trimmed.push("the least relevant experience bullet");
    } else break;
    current = structuredClone(current);
    result = await verifyPdf(current, matched);
  }
  return { resume: current, ...result, trimmed };
}
