import { cookies } from "next/headers";
import type { NextRequest } from "next/server";

import { getTailoredResume } from "@/lib/data";
import { renderDocx } from "@/lib/resume/render-docx";
import { renderPdf } from "@/lib/resume/render-pdf";
import { SESSION_COOKIE, verifySessionToken } from "@/lib/session";

// GET /api/resume/<id>?format=pdf|docx  → the tailored resume as a download
export async function GET(request: NextRequest, ctx: RouteContext<"/api/resume/[id]">) {
  const store = await cookies();
  if (!(await verifySessionToken(store.get(SESSION_COOKIE)?.value))) return new Response("Not signed in", { status: 401 });

  const { id } = await ctx.params;
  const row = Number.isInteger(Number(id)) ? await getTailoredResume(Number(id)) : null;
  if (!row) return new Response("Not found", { status: 404 });

  const format = request.nextUrl.searchParams.get("format") === "docx" ? "docx" : "pdf";
  const slug = (s: string) => s.replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40);
  const filename = `${slug(row.content.basics.name)}-${slug(row.company)}-${slug(row.title)}.${format}`;
  const body = format === "docx" ? await renderDocx(row.content) : await renderPdf(row.content);
  return new Response(new Uint8Array(body), {
    headers: {
      "Content-Type": format === "docx" ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document" : "application/pdf",
      "Content-Disposition": `attachment; filename="${filename}"`,
      "Cache-Control": "private, no-store",
    },
  });
}
