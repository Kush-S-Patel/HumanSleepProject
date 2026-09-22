"use client";

import type { Metrics } from "@/lib/types";
import { fmt, stageColor } from "@/lib/format";

export function StageDistribution({ metrics }: { metrics: Metrics }) {
  const rows = [
    { key: "W", label: "Wake", min: metrics.wake_min, pct: null as number | null },
    { key: "N1", label: "N1", min: metrics.n1_min, pct: metrics.n1_pct },
    { key: "N2", label: "N2", min: metrics.n2_min, pct: metrics.n2_pct },
    { key: "N3", label: "N3", min: metrics.n3_min, pct: metrics.n3_pct },
    { key: "REM", label: "REM", min: metrics.rem_min, pct: metrics.rem_pct },
  ];
  const maxMin = Math.max(1, ...rows.map((r) => r.min ?? 0));

  return (
    <div className="space-y-2.5">
      {rows.map((r) => (
        <div key={r.key} className="flex items-center gap-3">
          <div className="w-9 text-xs text-[var(--color-fog-400)]">{r.label}</div>
          <div className="flex-1 h-6 rounded-md bg-[var(--color-muted)] overflow-hidden">
            <div
              className="h-full rounded-md transition-all"
              style={{
                width: `${((r.min ?? 0) / maxMin) * 100}%`,
                background: stageColor[r.key],
                opacity: 0.85,
              }}
            />
          </div>
          <div className="w-24 text-right text-xs">
            <span className="stat-value text-[var(--color-fog-100)]">{fmt(r.min, 0)}</span>
            <span className="text-[var(--color-fog-500)]"> min</span>
            {r.pct != null && <span className="text-[var(--color-fog-500)]"> · {fmt(r.pct, 0)}%</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

export function RespiratoryMix({ metrics }: { metrics: Metrics }) {
  const parts = [
    { label: "Obstructive", value: metrics.n_obstructive_apnea, color: "#ff6b6b" },
    { label: "Central", value: metrics.n_central_apnea, color: "#ff9e64" },
    { label: "Mixed", value: metrics.n_mixed_apnea, color: "#ff8ab0" },
    { label: "Hypopnea", value: metrics.n_hypopnea, color: "#f2c14e" },
    { label: "RERA", value: metrics.n_rera, color: "#c3e88d" },
  ];
  const total = parts.reduce((s, p) => s + (p.value || 0), 0);

  return (
    <div>
      <div className="flex h-4 w-full overflow-hidden rounded bg-[var(--color-muted)]">
        {total === 0 ? (
          <div className="flex-1" />
        ) : (
          parts.map((p) => (
            <div
              key={p.label}
              style={{ width: `${(p.value / total) * 100}%`, background: p.color, opacity: 0.9 }}
              title={`${p.label}: ${p.value}`}
            />
          ))
        )}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-3">
        {parts.map((p) => (
          <div key={p.label} className="flex items-center gap-2 text-xs">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: p.color }} />
            <span className="text-[var(--color-fog-400)]">{p.label}</span>
            <span className="ml-auto stat-value text-[var(--color-fog-100)]">{p.value}</span>
          </div>
        ))}
      </div>
      {total === 0 && (
        <div className="mt-2 text-xs text-[var(--color-fog-500)]">No respiratory events scored.</div>
      )}
    </div>
  );
}
