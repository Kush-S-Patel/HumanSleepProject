import type { Severity } from "@/lib/types";
import { severityColor } from "@/lib/format";

export function SeverityBadge({ severity, label }: { severity: Severity; label?: string }) {
  const color = severityColor[severity];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs font-medium capitalize"
      style={{
        color,
        background: `color-mix(in srgb, ${color} 12%, white)`,
        border: `1px solid color-mix(in srgb, ${color} 28%, var(--color-line))`,
      }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
      {label ?? severity}
    </span>
  );
}

export function Chip({
  children,
  tone = "default",
}: {
  children: React.ReactNode;
  tone?: "default" | "teal" | "warn" | "muted";
}) {
  const tones: Record<string, string> = {
    default: "text-[var(--color-fog-300)] border-[var(--color-line)] bg-[var(--color-muted)]",
    teal: "text-[var(--color-teal)] border-[var(--color-line)] bg-[var(--color-muted)]",
    warn: "text-[var(--color-sev-mild)] border-[var(--color-line)] bg-[var(--color-muted)]",
    muted: "text-[var(--color-fog-500)] border-[var(--color-line)] bg-transparent",
  };
  return (
    <span className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[11px] ${tones[tone]}`}>
      {children}
    </span>
  );
}

export function StatCard({
  label,
  value,
  unit,
  sub,
  accent,
}: {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="panel-quiet px-4 py-3">
      <div className="text-[11px] uppercase tracking-[0.08em] text-[var(--color-fog-500)]">{label}</div>
      <div className="mt-1 flex items-baseline gap-1">
        <span className="stat-value text-[24px]" style={{ color: accent ?? "var(--color-fog-100)" }}>
          {value}
        </span>
        {unit && <span className="text-xs text-[var(--color-fog-400)]">{unit}</span>}
      </div>
      {sub && <div className="mt-0.5 text-[11px] text-[var(--color-fog-500)]">{sub}</div>}
    </div>
  );
}

export function SectionTitle({ children, kicker }: { children: React.ReactNode; kicker?: string }) {
  return (
    <div className="mb-3">
      {kicker && (
        <div className="text-[11px] uppercase tracking-[0.1em] text-[var(--color-fog-500)]">{kicker}</div>
      )}
      <h2 className="font-display text-lg text-[var(--color-fog-100)]" style={{ fontFamily: "var(--font-display)" }}>
        {children}
      </h2>
    </div>
  );
}
