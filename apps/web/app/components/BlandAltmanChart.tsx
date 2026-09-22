"use client";

import type { AhiAgreement, ConcordanceSession } from "@/lib/types";

export function BlandAltmanChart({
  agreement,
  sessions,
}: {
  agreement: AhiAgreement;
  sessions: ConcordanceSession[];
}) {
  const points =
    agreement.points ??
    sessions
      .filter((s) => s.human_ahi != null && s.caisr_ahi != null)
      .map((s) => {
        const human = s.human_ahi as number;
        const caisr = s.caisr_ahi as number;
        return {
          uid: s.uid,
          cohort: s.cohort,
          human,
          caisr,
          mean: (human + caisr) / 2,
          diff: human - caisr,
        };
      });

  if (points.length === 0) {
    return <div className="py-6 text-center text-sm text-[var(--color-fog-500)]">No paired AHI points.</div>;
  }

  const W = 520;
  const H = 280;
  const pad = { l: 48, r: 16, t: 16, b: 36 };
  const means = points.map((p) => p.mean);
  const diffs = points.map((p) => p.diff);
  const xMin = Math.min(...means);
  const xMax = Math.max(...means);
  const yAbs = Math.max(4, ...diffs.map(Math.abs), Math.abs(agreement.loa_upper ?? 0), Math.abs(agreement.loa_lower ?? 0));
  const x0 = pad.l;
  const y0 = pad.t;
  const pw = W - pad.l - pad.r;
  const ph = H - pad.t - pad.b;
  const xSpan = xMax - xMin || 1;
  const x = (v: number) => x0 + ((v - xMin) / xSpan) * pw;
  const y = (v: number) => y0 + ph / 2 - (v / yAbs) * (ph / 2);

  const bias = agreement.bias ?? 0;
  const loaL = agreement.loa_lower ?? bias;
  const loaU = agreement.loa_upper ?? bias;

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        <line x1={x0} y1={y(0)} x2={x0 + pw} y2={y(0)} stroke="var(--color-line)" strokeWidth={1} />
        <line
          x1={x0}
          y1={y(bias)}
          x2={x0 + pw}
          y2={y(bias)}
          stroke="var(--color-teal)"
          strokeWidth={1.5}
          strokeDasharray="4 3"
        />
        <line x1={x0} y1={y(loaU)} x2={x0 + pw} y2={y(loaU)} stroke="var(--color-sev-mild)" strokeWidth={1} strokeDasharray="2 3" />
        <line x1={x0} y1={y(loaL)} x2={x0 + pw} y2={y(loaL)} stroke="var(--color-sev-mild)" strokeWidth={1} strokeDasharray="2 3" />
        {points.map((p) => (
          <circle key={p.uid} cx={x(p.mean)} cy={y(p.diff)} r={5} fill="var(--color-teal)" opacity={0.85}>
            <title>
              {p.uid}: human {p.human.toFixed(1)} / CAISR {p.caisr.toFixed(1)}
            </title>
          </circle>
        ))}
        <text x={x0 + pw / 2} y={H - 8} textAnchor="middle" fontSize={11} fill="var(--color-fog-500)">
          Mean AHI (human + CAISR) / 2
        </text>
        <text
          x={14}
          y={y0 + ph / 2}
          textAnchor="middle"
          fontSize={11}
          fill="var(--color-fog-500)"
          transform={`rotate(-90 14 ${y0 + ph / 2})`}
        >
          Human − CAISR
        </text>
        <text x={x0 + 4} y={y(bias) - 4} fontSize={10} fill="var(--color-teal)">
          bias {bias.toFixed(1)}
        </text>
      </svg>
      <div className="mt-1 text-[11px] text-[var(--color-fog-500)]">
        Bland–Altman · n={points.length} · LoA {loaL.toFixed(1)} … {loaU.toFixed(1)} /h
      </div>
    </div>
  );
}
