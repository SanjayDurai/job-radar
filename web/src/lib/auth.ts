import "server-only";

import { cookies } from "next/headers";

import { SESSION_COOKIE, verifySessionToken } from "@/lib/session";

/** Server actions and API routes are public endpoints: check the session in each one, not only in proxy.ts. */
export async function requireSession() {
  const store = await cookies();
  if (!(await verifySessionToken(store.get(SESSION_COOKIE)?.value))) throw new Error("Not signed in");
}
