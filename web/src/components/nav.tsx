"use client";

import { BriefcaseIcon, Building2Icon, KanbanSquareIcon, SunriseIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";
import { cn } from "cn";

const LINKS = [
  { href: "/", label: "Today", icon: SunriseIcon },
  { href: "/jobs", label: "All jobs", icon: BriefcaseIcon },
  { href: "/tracker", label: "Tracker", icon: KanbanSquareIcon },
  { href: "/companies", label: "Companies", icon: Building2Icon },
];

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

/** Inline links in the header on wider screens. */
export function TopNav() {
  return (
    <Suspense fallback={<TopNavLinks pathname="" />}>
      <TopNavWithPath />
    </Suspense>
  );
}

function TopNavWithPath() {
  return <TopNavLinks pathname={usePathname()} />;
}

function TopNavLinks({ pathname }: { pathname: string }) {
  return (
    <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
      {LINKS.map(({ href, label }) => (
        <Link
          key={href}
          href={href}
          aria-current={isActive(pathname, href) ? "page" : undefined}
          className={cn(
            "rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground",
            "focus-visible:outline-2 focus-visible:outline-ring",
            isActive(pathname, href) && "bg-accent text-accent-foreground",
          )}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}

/** Thumb-reach tab bar on phones. */
export function BottomNav() {
  return (
    <Suspense fallback={<BottomNavLinks pathname="" />}>
      <BottomNavWithPath />
    </Suspense>
  );
}

function BottomNavWithPath() {
  return <BottomNavLinks pathname={usePathname()} />;
}

function BottomNavLinks({ pathname }: { pathname: string }) {
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t bg-card/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
    >
      {LINKS.map(({ href, label, icon: Icon }) => (
        <Link
          key={href}
          href={href}
          aria-current={isActive(pathname, href) ? "page" : undefined}
          className={cn(
            "flex flex-col items-center gap-0.5 py-2 text-[11px] font-medium text-muted-foreground",
            isActive(pathname, href) && "text-primary",
          )}
        >
          <Icon className="size-5" aria-hidden />
          {label}
        </Link>
      ))}
    </nav>
  );
}
