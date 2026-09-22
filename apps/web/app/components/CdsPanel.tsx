import type { Summary } from "@/lib/types";
import { severityColor } from "@/lib/format";
import { SeverityBadge } from "./ui";

const domainLabel: Record<string, string> = {
  respiratory: "Respiratory",
  oxygenation: "Oxygenation",
  architecture: "Sleep architecture",
  arousals: "Arousals",
  limb: "Limb movements",
};

export function CdsPanel({ summary }: { summary: Summary }) {
  return (
    <div className="panel p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.08em] text-[var(--color-fog-500)]">
            Decision support (research)
          </div>
          <h2
            className="font-display mt-1 text-xl leading-snug text-[var(--color-fog-100)]"
            style={{ fontFamily: "var(--font-display)" }}
          >
            {summary.headline}
          </h2>
        </div>
        <SeverityBadge severity={summary.overall_severity} />
      </div>

      <div className="mt-4 space-y-2.5">
        {summary.findings.length === 0 && (
          <div className="text-sm text-[var(--color-fog-400)]">
            No abnormal findings surfaced by automated review.
          </div>
        )}
        {summary.findings.map((f, i) => {
          const color = severityColor[f.severity];
          return (
            <div
              key={i}
              className="flex gap-3 rounded-xl border p-3"
              style={{
                borderColor: `color-mix(in srgb, ${color} 34%, transparent)`,
                background: `color-mix(in srgb, ${color} 8%, transparent)`,
              }}
            >
              <span className="mt-1 h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-500 text-[var(--color-fog-100)]">{f.title}</span>
                  <span className="text-[10px] uppercase tracking-wide text-[var(--color-fog-500)]">
                    {domainLabel[f.domain] ?? f.domain}
                  </span>
                </div>
                <div className="mt-0.5 text-[13px] leading-relaxed text-[var(--color-fog-400)]">{f.detail}</div>
              </div>
            </div>
          );
        })}
      </div>

      {summary.caveats.length > 0 && (
        <div className="mt-4 rounded-xl border border-[rgba(242,193,78,0.28)] bg-[rgba(242,193,78,0.07)] p-3">
          <div className="text-[11px] font-500 uppercase tracking-wide text-[var(--color-sev-mild)]">
            Interpretation caveats
          </div>
          <ul className="mt-1.5 space-y-1">
            {summary.caveats.map((c, i) => (
              <li key={i} className="text-[13px] leading-relaxed text-[var(--color-fog-300)]">
                • {c}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 border-t hairline pt-3 text-[11px] leading-relaxed text-[var(--color-fog-500)]">
        {summary.disclaimer}
      </div>
    </div>
  );
}
