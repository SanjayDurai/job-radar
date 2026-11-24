"use client";

import { RefreshCwIcon } from "lucide-react";
import { useTransition } from "react";
import { toast } from "sonner";

import { runNow } from "@/app/actions";
import { Button } from "@/components/ui/button";

export function RunNowButton() {
  const [pending, start] = useTransition();
  return (
    <Button
      variant="outline"
      size="sm"
      disabled={pending}
      onClick={() =>
        start(async () => {
          const res = await runNow();
          if (res.ok) toast.success(res.message);
          else toast.error(res.message);
        })
      }
    >
      <RefreshCwIcon className={pending ? "animate-spin" : undefined} aria-hidden />
      {pending ? "Starting…" : "Run now"}
    </Button>
  );
}
