import { RadarIcon } from "lucide-react";
import { Suspense } from "react";

import { LoginForm } from "./login-form";

export const metadata = { title: "Sign in" };

async function NextField({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  return <LoginForm next={next ?? "/"} />;
}

export default function LoginPage({ searchParams }: PageProps<"/login">) {
  return (
    <main className="grid min-h-dvh place-items-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2 text-lg font-semibold tracking-tight">
          <RadarIcon className="size-6 text-primary" aria-hidden />
          Job Radar
        </div>
        <Suspense fallback={<LoginForm next="/" />}>
          <NextField searchParams={searchParams as Promise<{ next?: string }>} />
        </Suspense>
      </div>
    </main>
  );
}
