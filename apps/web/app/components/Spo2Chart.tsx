"use client";

import { useMemo } from "react";
import type { ScoredEvent, Signals } from "@/lib/types";

export function Spo2Chart({
  signals,
  events,
  totalSec,
}: {
  signals: Signals | null;
  events: ScoredEvent[];
  totalSec: number;
}) {
  const W = 1000;
  const H = 190;
  const padL = 40;
  const padR = 12;
  const padT = 12;
  const padB = 24;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const yMin = 70;
  const yMax = 100;
  const y = (v: number) => padT + (1 - (Math.max(yMin, Math.min(yMax, v)) - yMin) / (yMax - yMin)) * plotH;

  const spo2 = signals?.channels?.SpO2 ?? null;
  const fs = signals?.fs ?? 1;

  const path = useMemo(() => {
    if (!spo2 || spo2.length === 0) return "";
    const step = Math.max(1, Math.floor(spo2.length / 1400));
    let d = "";
    for (let i = 0; i < spo2.length; i += step) {
      const t = i / fs;
      const px = padL + (t / Math.max(1, totalSec)) * plotW;
      const py = y(spo2[i]);
      d += `${d ? "L" : "M"} ${px.toFixed(1)} ${py.toFixed(1)} `;
    }
    return d;
  }, [spo2, fs, totalSec]);

  const nadirs = events.filter((e) => e.nadir_spo2 != null);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: "auto" }}>
      {[100, 90, 80, 70].map((v) => (
        <g key={v}>
          <line
            x1={padL}
            y1={y(v)}
            x2={W - padR}
            y2={y(v)}
            stroke={v === 90 ? "rgba(255,107,107,0.35)" : "rgba(35,48,79,0.5)"}
            strokeWidth={1}
            strokeDasharray={v === 90 ? "4 4" : undefined}
          />
          <text x={padL - 6} y={y(v) + 3} textAnchor="end" fontSize={10} fill="var(--color-fog-500)">
            {v}
          </text>
        </g>
      ))}

      {/* hypoxemia band below 90 */}
      <rect x={padL} y={y(90)} width={plotW} height={y(70) - y(90)} fill="rgba(255,107,107,0.06)" />

      {path ? (
        <path
          d={path}
          fill="none"
          stroke="var(--color-teal)"
          strokeWidth={1.6}
          strokeLinejoin="round"
          className="animate-sweep"
          style={{ ["--dash" as string]: 6000 } as React.CSSProperties}
          strokeDasharray={6000}
        />
      ) : (
        // Fallback: plot per-event nadirs when no signal preview is cached.
        nadirs.map((e, i) => {
          const px = padL + (e.onset_sec / Math.max(1, totalSec)) * plotW;
          return (
            <circle key={i} cx={px} cy={y(e.nadir_spo2!)} r={2.4} fill="var(--color-sev-severe)" opacity={0.8}>
              <title>{`Nadir ${e.nadir_spo2}%`}</title>
            </circle>
          );
        })
      )}

      {!path && nadirs.length === 0 && (
        <text x={W / 2} y={H / 2} textAnchor="middle" fontSize={12} fill="var(--color-fog-500)">
          No oximetry preview available for this study
        </text>
      )}
    </svg>
  );
}
