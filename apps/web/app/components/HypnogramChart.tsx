"use client";

import { useMemo, useState } from "react";
import type { ScoredEvent } from "@/lib/types";
import { eventColor, eventLabel, stageColor } from "@/lib/format";

const LEVELS = ["W", "REM", "N1", "N2", "N3"] as const;
const LEVEL_INDEX: Record<string, number> = { W: 0, REM: 1, N1: 2, N2: 3, N3: 4 };

const RAILS: { key: string; label: string; cats: string[] }[] = [
  { key: "resp", label: "Respiratory", cats: ["apnea_obstructive", "apnea_central", "apnea_mixed", "hypopnea", "rera"] },
  { key: "arousal", label: "Arousals", cats: ["arousal"] },
  { key: "limb", label: "Limb", cats: ["limb_movement"] },
];

function clockAt(startClock: string | null, offsetSec: number): string {
  if (!startClock) {
    const h = Math.floor(offsetSec / 3600);
    const m = Math.floor((offsetSec % 3600) / 60);
    return `${h}:${m.toString().padStart(2, "0")}`;
  }
  const [h0, m0, s0] = startClock.split(":").map((x) => parseInt(x, 10));
  let total = (h0 * 3600 + m0 * 60 + (s0 || 0) + offsetSec) % 86400;
  if (total < 0) total += 86400;
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}`;
}

export function HypnogramChart({
  stages,
  epochSec,
  startClock,
  events,
  onEpochClick,
}: {
  stages: string[];
  epochSec: number;
  startClock: string | null;
  events: ScoredEvent[];
  onEpochClick?: (epochIndex: number) => void;
}) {
  const W = 1000;
  const padL = 46;
  const padR = 12;
  const hypTop = 16;
  const rowH = 26;
  const hypH = rowH * LEVELS.length;
  const railGap = 14;
  const railH = 16;
  const railsTop = hypTop + hypH + 18;
  const H = railsTop + RAILS.length * (railH + railGap) + 26;

  const n = stages.length;
  const totalSec = n * epochSec;
  const plotW = W - padL - padR;
  const x = (sec: number) => padL + (sec / Math.max(1, totalSec)) * plotW;

  const [hover, setHover] = useState<{ i: number; px: number } | null>(null);

  const runs = useMemo(() => {
    const out: { start: number; end: number; stage: string }[] = [];
    let s = 0;
    for (let i = 1; i <= n; i++) {
      if (i === n || stages[i] !== stages[s]) {
        out.push({ start: s, end: i, stage: stages[s] });
        s = i;
      }
    }
    return out;
  }, [stages, n]);

  const connector = useMemo(() => {
    let d = "";
    let prevY: number | null = null;
    for (const r of runs) {
      if (r.stage === "?" || LEVEL_INDEX[r.stage] === undefined) {
        prevY = null;
        continue;
      }
      const y = hypTop + LEVEL_INDEX[r.stage] * rowH + rowH / 2;
      const xs = x(r.start * epochSec);
      const xe = x(r.end * epochSec);
      if (prevY !== null) d += `L ${xs.toFixed(1)} ${prevY.toFixed(1)} `;
      d += `${d ? "L" : "M"} ${xs.toFixed(1)} ${y.toFixed(1)} L ${xe.toFixed(1)} ${y.toFixed(1)} `;
      prevY = y;
    }
    return d;
  }, [runs, epochSec]);

  const ticks = useMemo(() => {
    const hours = Math.ceil(totalSec / 3600);
    const arr: number[] = [];
    for (let hsec = 0; hsec <= totalSec; hsec += 3600) arr.push(hsec);
    if (hours <= 0) arr.push(0);
    return arr;
  }, [totalSec]);

  return (
    <div className="w-full">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ height: "auto" }}
        onMouseLeave={() => setHover(null)}
      >
        {/* grid + stage labels */}
        {LEVELS.map((lvl, i) => {
          const y = hypTop + i * rowH + rowH / 2;
          return (
            <g key={lvl}>
              <line x1={padL} y1={y} x2={W - padR} y2={y} stroke="rgba(35,48,79,0.5)" strokeWidth={1} />
              <text x={padL - 8} y={y + 3} textAnchor="end" fontSize={11} fill="var(--color-fog-500)">
                {lvl}
              </text>
            </g>
          );
        })}

        {/* REM emphasis band */}
        {runs
          .filter((r) => r.stage === "REM")
          .map((r, i) => (
            <rect
              key={`rem${i}`}
              x={x(r.start * epochSec)}
              y={hypTop + LEVEL_INDEX.REM * rowH + 4}
              width={Math.max(1, x(r.end * epochSec) - x(r.start * epochSec))}
              height={rowH - 8}
              fill="var(--color-stage-rem)"
              opacity={0.16}
            />
          ))}

        {/* connectors */}
        <path
          d={connector}
          fill="none"
          stroke="rgba(120,140,190,0.4)"
          strokeWidth={1.4}
          className="animate-sweep"
          style={{ ["--dash" as string]: 4000 } as React.CSSProperties}
          strokeDasharray={4000}
        />

        {/* colored stage segments */}
        {runs.map((r, i) => {
          if (r.stage === "?" || LEVEL_INDEX[r.stage] === undefined) return null;
          const y = hypTop + LEVEL_INDEX[r.stage] * rowH + rowH / 2;
          return (
            <line
              key={i}
              x1={x(r.start * epochSec)}
              y1={y}
              x2={x(r.end * epochSec)}
              y2={y}
              stroke={stageColor[r.stage]}
              strokeWidth={3}
              strokeLinecap="round"
            />
          );
        })}

        {/* event rails */}
        {RAILS.map((rail, ri) => {
          const y0 = railsTop + ri * (railH + railGap);
          const evs = events.filter((e) => rail.cats.includes(e.category));
          return (
            <g key={rail.key}>
              <text x={padL - 8} y={y0 + railH / 2 + 3} textAnchor="end" fontSize={10} fill="var(--color-fog-500)">
                {rail.label}
              </text>
              <rect x={padL} y={y0} width={plotW} height={railH} rx={3} fill="var(--color-muted)" />
              {evs.map((e, i) => {
                const ex = x(e.onset_sec);
                const ew = Math.max(1.2, x(e.onset_sec + e.duration_sec) - ex);
                return (
                  <rect
                    key={i}
                    x={ex}
                    y={y0 + 2}
                    width={ew}
                    height={railH - 4}
                    fill={eventColor[e.category] ?? "var(--color-fog-400)"}
                    opacity={0.85}
                  >
                    <title>
                      {(eventLabel[e.category] ?? e.category)} · {clockAt(startClock, e.onset_sec)} ·{" "}
                      {e.duration_sec.toFixed(0)}s
                      {e.nadir_spo2 != null ? ` · nadir ${e.nadir_spo2}%` : ""}
                    </title>
                  </rect>
                );
              })}
            </g>
          );
        })}

        {/* time axis */}
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={x(t)} y1={hypTop} x2={x(t)} y2={railsTop - 6} stroke="rgba(35,48,79,0.35)" strokeWidth={1} />
            <text x={x(t)} y={H - 8} textAnchor="middle" fontSize={10} fill="var(--color-fog-500)">
              {clockAt(startClock, t)}
            </text>
          </g>
        ))}

        {/* hover interaction */}
        <rect
          x={padL}
          y={hypTop}
          width={plotW}
          height={hypH}
          fill="transparent"
          style={{ cursor: onEpochClick ? "pointer" : "crosshair" }}
          onMouseMove={(ev) => {
            const svg = ev.currentTarget.ownerSVGElement!;
            const pt = svg.createSVGPoint();
            pt.x = ev.clientX;
            pt.y = ev.clientY;
            const loc = pt.matrixTransform(svg.getScreenCTM()!.inverse());
            const frac = (loc.x - padL) / plotW;
            const i = Math.max(0, Math.min(n - 1, Math.floor(frac * n)));
            setHover({ i, px: x(i * epochSec) });
          }}
          onClick={(ev) => {
            if (!onEpochClick) return;
            const svg = ev.currentTarget.ownerSVGElement!;
            const pt = svg.createSVGPoint();
            pt.x = ev.clientX;
            pt.y = ev.clientY;
            const loc = pt.matrixTransform(svg.getScreenCTM()!.inverse());
            const frac = (loc.x - padL) / plotW;
            const i = Math.max(0, Math.min(n - 1, Math.floor(frac * n)));
            onEpochClick(i);
          }}
        />
        {hover && (
          <g>
            <line x1={hover.px} y1={hypTop} x2={hover.px} y2={hypTop + hypH} stroke="var(--color-teal)" strokeWidth={1} opacity={0.7} />
            <rect x={Math.min(hover.px + 6, W - 150)} y={hypTop} width={144} height={34} rx={6} fill="var(--color-surface)" stroke="var(--color-line)" />
            <text x={Math.min(hover.px + 14, W - 142)} y={hypTop + 15} fontSize={11} fill="var(--color-fog-100)">
              {clockAt(startClock, hover.i * epochSec)} · {stages[hover.i] === "?" ? "Unscored" : stages[hover.i]}
            </text>
            <text x={Math.min(hover.px + 14, W - 142)} y={hypTop + 28} fontSize={10} fill="var(--color-fog-500)">
              epoch {hover.i + 1} / {n}
              {onEpochClick ? " · click to QC" : ""}
            </text>
          </g>
        )}
      </svg>
    </div>
  );
}
