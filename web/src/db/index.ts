import "server-only";

import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";

import * as schema from "./schema";

// One small pool per server instance. `prepare: false` keeps it compatible with Neon's
// pooled (PgBouncer) connection string. The global cache stops dev hot-reloads leaking pools.
const globalForDb = globalThis as unknown as { radarSql?: ReturnType<typeof postgres> };

function client() {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is not set (see web/.env.example)");
  return postgres(url, { prepare: false, max: 5, idle_timeout: 20 });
}

const sql = globalForDb.radarSql ?? client();
if (process.env.NODE_ENV !== "production") globalForDb.radarSql = sql;

export const db = drizzle(sql, { schema });
export { schema };
