import { LogOutIcon, RadarIcon } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { logout } from "@/app/actions";
import { BottomNav, TopNav } from "@/components/nav";
import { StatsStrip, StatsStripSkeleton } from "@/components/stats-strip";
import { ThemeToggle } from "@/components/theme";
import { Button } from "@/components/ui/button";

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="min-h-dvh pb-20 md:pb-10">
      <header className="sticky top-0 z-30 border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-4">
          <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
            <RadarIcon className="size-5 text-primary" aria-hidden />
            Job Radar
          </Link>
          <TopNav />
          <div className="ml-auto flex items-center gap-1">
            <ThemeToggle />
            <form action={logout}>
              <Button variant="ghost" size="icon" type="submit" aria-label="Sign out">
                <LogOutIcon />
              </Button>
            </form>
          </div>
        </div>
      </header>
      <div className="mx-auto max-w-6xl px-4">
        <div className="border-b py-3">
          <Suspense fallback={<StatsStripSkeleton />}>
            <StatsStrip />
          </Suspense>
        </div>
        <main className="py-6">{children}</main>
      </div>
      <BottomNav />
    </div>
  );
}
