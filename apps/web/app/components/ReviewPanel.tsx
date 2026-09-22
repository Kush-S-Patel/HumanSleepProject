"use client";

import { useState } from "react";
import type { ReviewState } from "@/lib/types";
import { updateReview } from "@/lib/api";
import { SectionTitle } from "@/app/components/ui";

const STATUSES: { id: ReviewState["status"]; label: string; hint: string }[] = [
  { id: "pending_review", label: "Pending", hint: "In queue" },
  { id: "in_review", label: "In review", hint: "Opened by scorer" },
  { id: "reviewed", label: "Reviewed", hint: "QC complete" },
  { id: "signed_off", label: "Signed off", hint: "Locked for export" },
];

export function ReviewPanel({
  uid,
  review,
  onChanged,
}: {
  uid: string;
  review: ReviewState | null;
  onChanged: () => void;
}) {
  const [reviewer, setReviewer] = useState(review?.reviewer ?? "");
  const [notes, setNotes] = useState(review?.notes ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const status = review?.status ?? "pending_review";

  const save = async (next: ReviewState["status"]) => {
    setBusy(true);
    setErr(null);
    try {
      await updateReview(uid, {
        status: next,
        reviewer: reviewer || undefined,
        notes: notes || undefined,
      });
      onChanged();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel p-5">
      <SectionTitle kicker="Clinic workflow">Review &amp; sign-off</SectionTitle>
      <p className="mb-3 text-[12px] leading-relaxed text-[var(--color-fog-500)]">
        AI scores land as pending. A tech/physician reviews epoch QC, then signs off before
        exporting the clinician report. Signed-off studies lock stage/event edits.
      </p>

      <div className="flex flex-wrap gap-1.5">
        {STATUSES.map((s) => (
          <button
            key={s.id}
            type="button"
            disabled={busy}
            onClick={() => save(s.id)}
            className={`rounded px-2.5 py-1.5 text-[12px] transition-colors ${
              status === s.id
                ? "bg-[var(--color-teal)] text-white"
                : "bg-[var(--color-muted)] text-[var(--color-fog-300)] hover:bg-[var(--color-line)]"
            }`}
            title={s.hint}
          >
            {s.label}
          </button>
        ))}
      </div>

      <label className="mt-3 block text-[11px] uppercase tracking-wide text-[var(--color-fog-500)]">
        Reviewer
        <input
          value={reviewer}
          onChange={(e) => setReviewer(e.target.value)}
          placeholder="e.g. Dr. Lee / RPSGT Kim"
          className="field-input mt-1 w-full"
        />
      </label>
      <label className="mt-2 block text-[11px] uppercase tracking-wide text-[var(--color-fog-500)]">
        Notes
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          placeholder="QC notes, caveats for referring MD…"
          className="field-input mt-1 w-full resize-y"
        />
      </label>
      <button
        type="button"
        disabled={busy}
        onClick={() => save(status)}
        className="btn-primary mt-3 w-full justify-center"
      >
        Save notes
      </button>
      {status === "signed_off" && (
        <div className="mt-3 rounded border border-[var(--color-teal)]/30 bg-[var(--color-muted)] px-3 py-2 text-[12px] text-[var(--color-teal)]">
          Signed off{review?.reviewer ? ` by ${review.reviewer}` : ""}. Reopen to “Reviewed” to unlock QC
          edits.
        </div>
      )}
      {err && <div className="mt-2 text-sm text-[var(--color-sev-severe)]">{err}</div>}
    </div>
  );
}
