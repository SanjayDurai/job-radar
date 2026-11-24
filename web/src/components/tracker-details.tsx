"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { saveTrackerDetails } from "@/app/actions";
import { Button } from "@/components/ui/button";

export function TrackerDetailsForm({ jobId, notes, appliedOn }: { jobId: number; notes: string | null; appliedOn: string | null }) {
  const [text, setText] = useState(notes ?? "");
  const [date, setDate] = useState(appliedOn ?? "");
  const [pending, start] = useTransition();
  const dirty = text !== (notes ?? "") || date !== (appliedOn ?? "");
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        start(async () => {
          await saveTrackerDetails(jobId, text, date || null);
          toast.success("Notes saved");
        });
      }}
    >
      <label className="block text-sm font-medium">
        Notes
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={4}
          placeholder="Referral from…, recruiter name, interview dates"
          className="mt-1 block w-full rounded-md border border-input bg-card p-2.5 text-sm font-normal focus-visible:outline-2 focus-visible:outline-ring"
        />
      </label>
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm font-medium">
          Applied on
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="mt-1 block h-9 rounded-md border border-input bg-card px-2.5 text-sm font-normal focus-visible:outline-2 focus-visible:outline-ring"
          />
        </label>
        <Button type="submit" size="sm" disabled={!dirty || pending}>
          {pending ? "Saving…" : "Save notes"}
        </Button>
      </div>
    </form>
  );
}
