"use client";

import { useActionState } from "react";

import { login } from "@/app/actions";
import { Button } from "@/components/ui/button";

export function LoginForm({ next }: { next: string }) {
  const [state, action, pending] = useActionState(login, undefined);
  return (
    <form action={action} className="space-y-4 rounded-lg border bg-card p-5">
      <input type="hidden" name="next" value={next} />
      <label className="block text-sm font-medium">
        Password
        <input
          type="password"
          name="password"
          required
          autoFocus
          autoComplete="current-password"
          aria-describedby={state?.error ? "login-error" : undefined}
          className="mt-1 block h-10 w-full rounded-md border border-input bg-background px-3 text-base focus-visible:outline-2 focus-visible:outline-ring"
        />
      </label>
      {state?.error && (
        <p id="login-error" role="alert" className="text-sm text-destructive">
          {state.error}
        </p>
      )}
      <Button type="submit" className="h-10 w-full" disabled={pending}>
        {pending ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
