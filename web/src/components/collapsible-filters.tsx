"use client";

import { SlidersHorizontalIcon } from "lucide-react";
import { useState } from "react";
import { cn } from "cn";

import { Button } from "@/components/ui/button";

/** On phones the filter form folds behind a button; on wider screens it's always shown. */
export function CollapsibleFilters({ activeCount, children }: { activeCount: number; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <Button variant="outline" size="sm" className="mb-3 md:hidden" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <SlidersHorizontalIcon aria-hidden />
        {open ? "Hide filters" : activeCount ? `Filters (${activeCount} on)` : "Filters"}
      </Button>
      <div className={cn(open ? "block" : "hidden", "md:block")}>{children}</div>
    </div>
  );
}
