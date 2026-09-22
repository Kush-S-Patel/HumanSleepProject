"use client";

import { useMemo, useState } from "react";
import type { ScoredEvent } from "@/lib/types";
import { eventColor, eventLabel, stageColor } from "@/lib/format";
import { overrideEvent, overrideStage } from "@/lib/api";

const STAGES = ["W", "N1", "N2", "N3", "REM", "?"] as const;

function pickTrace(
  traces: Record<string, number[]>,
  keys: string[],
): { name: string; values: number[] } | null {
  for (const k of keys) {
    for (const [name, values] of Object.entries(traces)) {
      if (name.toLowerCase().includes(k)) return { name, values };
    }
  }
  return null;
}

function Spark({
  values,
  color,
  label,
}: {
  values: number[];
  color: string;
  label: string;
}) {
  const W = 480;
  const H = 56;
  const path = useMemo(() => {
    if (!values.length) return "";
    const lo = Math.min(...values);
    const hi = Math.max(...values);
    const span = hi - lo || 1;
    return values
      .map((v, i) => {
        const x = (i / Math.max(1, values.length - 1)) * W;
        const y = H - 4 - ((v - lo) / span) * (H - 8);
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }, [values]);

  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-[11px] text-[var(--color-fog-500)]">
        <span className="font-mono">{label}</span>
        <span>
          {values.length
            ? `${Math.min(...values).toFixed(1)} – ${Math.max(...values).toFixed(1)}`
            : "no data"}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded border hairline bg-[var(--color-muted)]">
        {path ? <path d={path} fill="none" stroke={color} strokeWidth={1.5} /> : null}
      </svg>
    </div>
  );
}

export function EpochQcPanel({
  uid,
  epochIndex,
  epochSec,
  stage,
  traces,
  fs,
  windowStart,
  windowEnd,
  events,
  onClose,
  onUpdated,
}: {
  uid: string;
  epochIndex: number;
  epochSec: number;
  stage: string;
  traces: Record<string, number[]>;
  fs: number;
  windowStart: number;
  windowEnd: number;
  events: ScoredEvent[];
  onClose: () => void;
  onUpdated: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const eeg = pickTrace(traces, ["c4", "c3", "eeg"]);
  const flow = pickTrace(traces, ["ptaf", "airflow", "flow"]);
  const spo2 = pickTrace(traces, ["spo2", "sao2"]);

  const setStage = async (s: string) => {
    setBusy(true);
    setErr(null);
    try {
      await overrideStage(uid, epochIndex, s);
      onUpdated();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const removeEvent = async (index: number) => {
    setBusy(true);
    setErr(null);
    try {
      // Map window-local index to global by matching onset+category
      const target = events[index];
      const all = await (await import("@/lib/api")).fetchEvents(uid);
      const globalIdx = all.events.findIndex(
        (e) =>
          Math.abs(e.onset_sec - target.onset_sec) < 0.05 &&
          e.category === target.category &&
          Math.abs(e.duration_sec - target.duration_sec) < 0.05,
      );
      if (globalIdx < 0) throw new Error("could not locate event");
      await overrideEvent(uid, { action: "delete", index: globalIdx });
      onUpdated();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel mt-4 border border-[var(--color-teal)]/30 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.14em] text-[var(--color-fog-500)]">
            Epoch QC
          </div>
          <div className="mt-0.5 text-sm text-[var(--color-fog-200)]">
            Epoch {epochIndex + 1} · {windowStart.toFixed(0)}–{windowEnd.toFixed(0)}s · current{" "}
            <span className="font-mono" style={{ color: stageColor[stage] ?? "inherit" }}>
              {stage}
            </span>
            <span className="text-[var(--color-fog-500)]"> · {epochSec}s</span>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-sm text-[var(--color-fog-500)] hover:text-[var(--color-fog-200)]"
        >
          Close
        </button>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {STAGES.map((s) => (
          <button
            key={s}
            type="button"
            disabled={busy || s === stage}
            onClick={() => setStage(s)}
            className={`rounded px-2.5 py-1 text-xs font-mono transition-colors ${
              s === stage
                ? "bg-[var(--color-teal)] text-white"
                : "bg-[var(--color-muted)] text-[var(--color-fog-300)] hover:bg-[var(--color-line)]"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      <div className="mt-4 space-y-3">
        {eeg ? <Spark values={eeg.values} color="var(--color-stage-n2)" label={`EEG · ${eeg.name}`} /> : null}
        {flow ? <Spark values={flow.values} color="var(--color-cyan)" label={`Flow · ${flow.name}`} /> : null}
        {spo2 ? <Spark values={spo2.values} color="var(--color-sev-moderate)" label={`SpO₂ · ${spo2.name}`} /> : null}
        {!eeg && !flow && !spo2 ? (
          <div className="py-4 text-center text-sm text-[var(--color-fog-500)]">
            No preview waveforms for this study (re-score an EDF upload to extract EEG/flow/SpO₂).
          </div>
        ) : null}
      </div>

      <div className="mt-4">
        <div className="mb-2 text-[11px] uppercase tracking-[0.14em] text-[var(--color-fog-500)]">
          Events in window
        </div>
        {events.length === 0 ? (
          <div className="text-sm text-[var(--color-fog-500)]">None</div>
        ) : (
          <ul className="space-y-1.5">
            {events.map((e, i) => (
              <li
                key={`${e.onset_sec}-${i}`}
                className="flex items-center gap-2 text-sm text-[var(--color-fog-300)]"
              >
                <span className="h-2 w-2 rounded-sm" style={{ background: eventColor[e.category] }} />
                <span>{eventLabel[e.category] ?? e.category}</span>
                <span className="font-mono text-[12px] text-[var(--color-fog-500)]">
                  {e.onset_sec.toFixed(0)}s · {e.duration_sec.toFixed(0)}s
                  {e.nadir_spo2 != null ? ` · ${e.nadir_spo2}%` : ""}
                </span>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => removeEvent(i)}
                  className="ml-auto text-[11px] text-[var(--color-sev-severe)] hover:underline"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {err && <div className="mt-3 text-sm text-[var(--color-sev-severe)]">{err}</div>}
      <div className="mt-2 text-[11px] text-[var(--color-fog-500)]">
        Preview fs ≈ {fs} Hz. Overrides recompute AHI / CDS and are logged in provenance.
      </div>
    </div>
  );
}
