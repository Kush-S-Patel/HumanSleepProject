"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  exportUrl,
  fetchComparison,
  fetchEpochWindow,
  fetchEvents,
  fetchHypnogram,
  fetchReview,
  fetchSignals,
  fetchStudy,
} from "@/lib/api";
import type {
  EpochWindow,
  Hypnogram,
  ReviewState,
  ScoredEvent,
  Signals,
  StudyComparison,
  StudyReport,
} from "@/lib/types";
import {
  ageLabel,
  eventColor,
  eventLabel,
  fmt,
  minutesToHms,
  prettyStudyType,
  severityColor,
} from "@/lib/format";
import { Chip, SectionTitle, SeverityBadge, StatCard } from "@/app/components/ui";
import { CdsPanel } from "@/app/components/CdsPanel";
import { HypnogramChart } from "@/app/components/HypnogramChart";
import { Spo2Chart } from "@/app/components/Spo2Chart";
import { RespiratoryMix, StageDistribution } from "@/app/components/Distributions";
import { EpochQcPanel } from "@/app/components/EpochQcPanel";
import { ReviewPanel } from "@/app/components/ReviewPanel";

type Tab = "respiratory" | "architecture" | "events";

export default function StudyPage() {
  const params = useParams<{ uid: string }>();
  const uid = decodeURIComponent(params.uid);

  const [report, setReport] = useState<StudyReport | null>(null);
  const [hyp, setHyp] = useState<Hypnogram | null>(null);
  const [events, setEvents] = useState<ScoredEvent[]>([]);
  const [signals, setSignals] = useState<Signals | null>(null);
  const [comparison, setComparison] = useState<StudyComparison | null>(null);
  const [review, setReview] = useState<ReviewState | null>(null);
  const [epochQc, setEpochQc] = useState<EpochWindow | null>(null);
  const [tab, setTab] = useState<Tab>("respiratory");
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    setError(null);
    fetchStudy(uid).then(setReport).catch((e) => setError(String(e)));
    fetchHypnogram(uid).then(setHyp).catch(() => {});
    fetchEvents(uid)
      .then((d) => setEvents(d.events))
      .catch(() => {});
    fetchSignals(uid)
      .then(setSignals)
      .catch(() => setSignals(null));
    fetchComparison(uid)
      .then(setComparison)
      .catch(() => setComparison(null));
    fetchReview(uid)
      .then(setReview)
      .catch(() => setReview(null));
  }, [uid]);

  useEffect(() => {
    reload();
  }, [reload]);

  const openEpoch = async (i: number) => {
    try {
      const win = await fetchEpochWindow(uid, i);
      setEpochQc(win);
    } catch {
      setEpochQc({
        epoch_index: i,
        stage: hyp?.stages[i] ?? "?",
        epoch_length_sec: hyp?.epoch_length_sec ?? 30,
        window_start_sec: i * (hyp?.epoch_length_sec ?? 30),
        window_end_sec: (i + 1) * (hyp?.epoch_length_sec ?? 30),
        fs: 2,
        traces: {},
        events: events.filter((e) => {
          const t0 = i * (hyp?.epoch_length_sec ?? 30);
          const t1 = t0 + (hyp?.epoch_length_sec ?? 30);
          return e.onset_sec < t1 && e.onset_sec + e.duration_sec > t0;
        }),
        stages_nearby: [],
      });
    }
  };

  if (error) {
    return (
      <div className="panel p-8">
        <div className="text-[var(--color-sev-severe)]">Could not load study.</div>
        <div className="mt-2 text-sm text-[var(--color-fog-400)]">{error}</div>
        <Link href="/" className="mt-4 inline-block text-sm text-[var(--color-teal)]">
          ← Back to worklist
        </Link>
      </div>
    );
  }

  if (!report) {
    return <div className="panel p-8 text-[var(--color-fog-400)]">Loading study…</div>;
  }

  const { meta, metrics, summary } = report;
  const totalSec = (hyp?.stages.length ?? 0) * (hyp?.epoch_length_sec ?? 30);
  const prov = meta.provenance;

  return (
    <div className="space-y-6">
      <div className="animate-rise">
        <Link href="/" className="text-sm text-[var(--color-fog-400)] hover:text-[var(--color-teal)]">
          ← Worklist
        </Link>
        <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-[12px] text-[var(--color-fog-500)]">
              Study report
              <span className="font-mono text-[var(--color-fog-400)]">{meta.uid}</span>
            </div>
            <h1
              className="font-display mt-1 text-[1.65rem] text-[var(--color-fog-100)]"
              style={{ fontFamily: "var(--font-display)" }}
            >
              {meta.display_name ?? `Patient ${meta.patient_uid}`}
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-[var(--color-fog-400)]">
              <Chip tone={meta.population === "pediatric" ? "warn" : "default"}>{meta.cohort}</Chip>
              <span>{ageLabel(meta.age, meta.population)}</span>
              {meta.sex && <span>· {meta.sex}</span>}
              <span>· {prettyStudyType(meta.study_type)}</span>
              <Chip tone="teal">
                {meta.annotation_source === "caisr"
                  ? "CAISR"
                  : meta.annotation_source === "synthetic"
                    ? "Demo"
                    : "Human scored"}
              </Chip>
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <SeverityBadge severity={summary.overall_severity} label={`${summary.overall_severity} overall`} />
            <div className="flex flex-wrap justify-end gap-1.5">
              {(
                [
                  ["pdf", "PDF"],
                  ["html", "HTML"],
                  ["json", "JSON"],
                  ["bids.tsv", "BIDS TSV"],
                ] as const
              ).map(([kind, label]) => (
                <a
                  key={kind}
                  href={exportUrl(uid, kind)}
                  className="rounded border hairline bg-[var(--color-surface)] px-2.5 py-1 text-[11px] text-[var(--color-fog-300)] hover:border-[var(--color-teal)] hover:text-[var(--color-teal)]"
                  target="_blank"
                  rel="noreferrer"
                >
                  {label}
                </a>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <StatCard
          label="AHI"
          value={fmt(metrics.ahi, 1)}
          unit="/h"
          accent={severityColor[summary.osa_severity]}
          sub={`${summary.osa_severity} OSA`}
        />
        <StatCard label="RDI" value={fmt(metrics.rdi, 1)} unit="/h" />
        <StatCard label="Arousal idx" value={fmt(metrics.arousal_index, 1)} unit="/h" />
        <StatCard
          label="SpO₂ nadir"
          value={fmt(metrics.spo2_nadir, 0)}
          unit="%"
          accent={metrics.spo2_nadir != null && metrics.spo2_nadir < 90 ? "var(--color-sev-moderate)" : undefined}
        />
        <StatCard label="Total sleep" value={minutesToHms(metrics.total_sleep_time_min)} />
        <StatCard
          label="Efficiency"
          value={fmt(metrics.sleep_efficiency_pct, 0)}
          unit="%"
          accent={
            metrics.sleep_efficiency_pct != null && metrics.sleep_efficiency_pct < 85
              ? "var(--color-sev-mild)"
              : undefined
          }
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <div className="panel p-5">
            <SectionTitle kicker="Whole-night architecture">Hypnogram &amp; event rail</SectionTitle>
            <p className="mb-3 text-[12px] text-[var(--color-fog-500)]">
              Click an epoch to open QC: EEG / flow / SpO₂ preview and stage or event overrides.
            </p>
            {hyp && hyp.stages.length > 0 ? (
              <HypnogramChart
                stages={hyp.stages}
                epochSec={hyp.epoch_length_sec}
                startClock={hyp.start_clock}
                events={events}
                onEpochClick={openEpoch}
              />
            ) : (
              <div className="py-10 text-center text-sm text-[var(--color-fog-500)]">
                No sleep staging available for this study.
              </div>
            )}
            {epochQc && (
              <EpochQcPanel
                uid={uid}
                epochIndex={epochQc.epoch_index}
                epochSec={epochQc.epoch_length_sec}
                stage={epochQc.stage}
                traces={epochQc.traces}
                fs={epochQc.fs}
                windowStart={epochQc.window_start_sec}
                windowEnd={epochQc.window_end_sec}
                events={epochQc.events}
                onClose={() => setEpochQc(null)}
                onUpdated={() => {
                  reload();
                  openEpoch(epochQc.epoch_index);
                }}
              />
            )}
          </div>

          <div className="panel p-5">
            <div className="mb-4 flex items-center gap-2">
              {(["respiratory", "architecture", "events"] as Tab[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`rounded-full px-4 py-1.5 text-sm capitalize transition-colors ${
                    tab === t
                      ? "bg-[var(--color-teal)] font-500 text-white"
                      : "text-[var(--color-fog-400)] hover:bg-[var(--color-muted)]"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>

            {tab === "respiratory" && (
              <div className="space-y-5">
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <MiniStat label="Obstructive AI" value={fmt(metrics.obstructive_apnea_index, 1)} />
                  <MiniStat label="Central AI" value={fmt(metrics.central_apnea_index, 1)} />
                  <MiniStat label="Hypopnea idx" value={fmt(metrics.hypopnea_index, 1)} />
                  <MiniStat label="ODI" value={fmt(metrics.odi, 1)} />
                </div>
                <div>
                  <div className="mb-2 text-sm text-[var(--color-fog-400)]">Respiratory event composition</div>
                  <RespiratoryMix metrics={metrics} />
                </div>
                <div>
                  <div className="mb-1 flex items-center justify-between text-sm text-[var(--color-fog-400)]">
                    <span>Overnight oximetry</span>
                    {signals?.synthetic && (
                      <span className="text-[11px] text-[var(--color-fog-500)]">reconstructed preview</span>
                    )}
                    {prov?.spo2_from_waveform && (
                      <span className="text-[11px] text-[var(--color-teal)]">nadir/ODI from waveform</span>
                    )}
                  </div>
                  <Spo2Chart signals={signals} events={events} totalSec={totalSec} />
                </div>
              </div>
            )}

            {tab === "architecture" && (
              <div className="space-y-5">
                <StageDistribution metrics={metrics} />
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <MiniStat label="Sleep latency" value={minutesToHms(metrics.sleep_latency_min)} />
                  <MiniStat label="REM latency" value={minutesToHms(metrics.rem_latency_min)} />
                  <MiniStat label="WASO" value={minutesToHms(metrics.waso_min)} />
                  <MiniStat label="Fragmentation" value={fmt(metrics.sleep_fragmentation_index, 1)} unit="/h" />
                </div>
              </div>
            )}

            {tab === "events" && <EventsTable events={events} startClock={hyp?.start_clock ?? null} />}
          </div>
        </div>

        <div className="space-y-6">
          <ReviewPanel uid={uid} review={review} onChanged={reload} />
          <CdsPanel summary={summary} />

          {comparison && (
            <div className="panel p-5">
              <SectionTitle kicker="Validation">AI vs human</SectionTitle>
              <table className="mt-2 w-full text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wide text-[var(--color-fog-500)]">
                    <th className="py-1">Metric</th>
                    <th className="py-1">Human</th>
                    <th className="py-1">CAISR</th>
                  </tr>
                </thead>
                <tbody>
                  {(
                    [
                      ["ahi", "AHI"],
                      ["rdi", "RDI"],
                      ["arousal_index", "Arousal idx"],
                      ["spo2_nadir", "SpO₂ nadir"],
                      ["odi", "ODI"],
                      ["staging_kappa", "κ"],
                      ["staging_accuracy", "Accuracy"],
                    ] as const
                  ).map(([key, label]) => {
                    const h = comparison.human[key];
                    const a = comparison.ai[key];
                    if (h == null && a == null) return null;
                    return (
                      <tr key={key} className="border-t hairline">
                        <td className="py-1.5 text-[var(--color-fog-400)]">{label}</td>
                        <td className="py-1.5 font-mono text-[var(--color-fog-200)]">
                          {h == null ? "—" : Number(h).toFixed(1)}
                        </td>
                        <td className="py-1.5 font-mono text-[var(--color-fog-200)]">
                          {a == null ? "—" : Number(a).toFixed(1)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {comparison.source && (
                <div className="mt-2 text-[11px] text-[var(--color-fog-500)]">Source: {comparison.source}</div>
              )}
            </div>
          )}

          <div className="panel p-5">
            <SectionTitle kicker="Provenance">How this report was made</SectionTitle>
            {prov ? (
              <dl className="mt-2 space-y-2 text-sm">
                <ProvRow label="Scorer" value={prov.scorer ?? meta.annotation_source} />
                <ProvRow label="psg_core" value={prov.psg_core_version ?? "—"} />
                {prov.source_filename && <ProvRow label="Source file" value={prov.source_filename} />}
                {prov.pipeline && <ProvRow label="Pipeline" value={prov.pipeline} />}
                {prov.created_at && <ProvRow label="Created" value={prov.created_at.slice(0, 19)} />}
                {prov.sanitize_steps && prov.sanitize_steps.length > 0 && (
                  <div>
                    <div className="text-[11px] uppercase tracking-wide text-[var(--color-fog-500)]">
                      Sanitize / enrich
                    </div>
                    <ul className="mt-1 list-inside list-disc text-[12px] text-[var(--color-fog-300)]">
                      {prov.sanitize_steps.map((s) => (
                        <li key={s} className="font-mono">
                          {s}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {prov.caisr_images && (
                  <div>
                    <div className="text-[11px] uppercase tracking-wide text-[var(--color-fog-500)]">
                      CAISR images
                    </div>
                    <div className="mt-1 font-mono text-[11px] leading-relaxed text-[var(--color-fog-400)]">
                      {prov.caisr_images.join(", ")}
                    </div>
                  </div>
                )}
              </dl>
            ) : (
              <div className="text-sm text-[var(--color-fog-500)]">
                Source: {meta.annotation_source}. Re-score an upload to attach full provenance.
              </div>
            )}
          </div>

          <div className="panel p-5">
            <SectionTitle kicker="Event tally">Scored events</SectionTitle>
            <div className="space-y-2 text-sm">
              <TallyRow label="Obstructive apnea" value={metrics.n_obstructive_apnea} cat="apnea_obstructive" />
              <TallyRow label="Central apnea" value={metrics.n_central_apnea} cat="apnea_central" />
              <TallyRow label="Mixed apnea" value={metrics.n_mixed_apnea} cat="apnea_mixed" />
              <TallyRow label="Hypopnea" value={metrics.n_hypopnea} cat="hypopnea" />
              <TallyRow label="RERA" value={metrics.n_rera} cat="rera" />
              <TallyRow label="Arousals" value={metrics.n_arousals} cat="arousal" />
              <TallyRow label="Limb movements" value={metrics.n_limb_movements} cat="limb_movement" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ProvRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-3">
      <dt className="w-24 shrink-0 text-[11px] uppercase tracking-wide text-[var(--color-fog-500)]">{label}</dt>
      <dd className="font-mono text-[12px] text-[var(--color-fog-200)] break-all">{value}</dd>
    </div>
  );
}

function MiniStat({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="panel-quiet px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--color-fog-500)]">{label}</div>
      <div className="mt-0.5 flex items-baseline gap-1">
        <span className="stat-value text-[18px] text-[var(--color-fog-100)]">{value}</span>
        {unit && <span className="text-[11px] text-[var(--color-fog-500)]">{unit}</span>}
      </div>
    </div>
  );
}

function TallyRow({ label, value, cat }: { label: string; value: number; cat: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="h-2.5 w-2.5 rounded-sm" style={{ background: eventColor[cat] }} />
      <span className="text-[var(--color-fog-400)]">{label}</span>
      <span className="ml-auto stat-value text-[var(--color-fog-100)]">{value}</span>
    </div>
  );
}

function EventsTable({ events, startClock }: { events: ScoredEvent[]; startClock: string | null }) {
  const clockAt = (offsetSec: number) => {
    if (!startClock) {
      const h = Math.floor(offsetSec / 3600);
      const m = Math.floor((offsetSec % 3600) / 60);
      const s = Math.floor(offsetSec % 60);
      return `${h}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
    }
    const [h0, m0, s0] = startClock.split(":").map((x) => parseInt(x, 10));
    let total = (h0 * 3600 + m0 * 60 + (s0 || 0) + offsetSec) % 86400;
    if (total < 0) total += 86400;
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = Math.floor(total % 60);
    return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  if (events.length === 0) {
    return <div className="py-8 text-center text-sm text-[var(--color-fog-500)]">No events scored.</div>;
  }

  return (
    <div className="max-h-[420px] overflow-auto rounded-lg border hairline">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-[var(--color-surface)] text-left text-[11px] uppercase tracking-wide text-[var(--color-fog-500)]">
          <tr>
            <th className="px-3 py-2 font-500">Onset</th>
            <th className="px-3 py-2 font-500">Type</th>
            <th className="px-3 py-2 font-500">Detail</th>
            <th className="px-3 py-2 font-500 text-right">Dur</th>
            <th className="px-3 py-2 font-500 text-right">Nadir</th>
          </tr>
        </thead>
        <tbody>
          {events.slice(0, 600).map((e, i) => (
            <tr key={i} className="border-t border-[rgba(35,48,79,0.12)]">
              <td className="px-3 py-1.5 font-mono text-[12px] text-[var(--color-fog-300)]">{clockAt(e.onset_sec)}</td>
              <td className="px-3 py-1.5">
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-sm" style={{ background: eventColor[e.category] }} />
                  <span className="text-[var(--color-fog-200)]">{eventLabel[e.category] ?? e.category}</span>
                </span>
              </td>
              <td className="px-3 py-1.5 text-[var(--color-fog-500)]">{e.subtype}</td>
              <td className="px-3 py-1.5 text-right text-[var(--color-fog-400)]">{e.duration_sec.toFixed(0)}s</td>
              <td className="px-3 py-1.5 text-right text-[var(--color-fog-400)]">
                {e.nadir_spo2 != null ? `${e.nadir_spo2}%` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
