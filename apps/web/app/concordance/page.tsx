"use client";

import { useEffect, useState } from "react";
import { fetchConcordance } from "@/lib/api";
import type { ConcordanceReport } from "@/lib/types";
import { SectionTitle, StatCard, Chip } from "@/app/components/ui";
import { BlandAltmanChart } from "@/app/components/BlandAltmanChart";
import Link from "next/link";

const fmt = (v: number | null | undefined, d = 3) =>
  v === null || v === undefined ? "—" : v.toFixed(d);

export default function ConcordancePage() {
  const [report, setReport] = useState<ConcordanceReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchConcordance()
      .then(setReport)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="animate-rise">
        <div className="text-[12px] text-[var(--color-fog-500)]">Validation · CAISR vs human</div>
        <h1
          className="font-display mt-1.5 text-[1.75rem] leading-snug text-[var(--color-fog-100)]"
          style={{ fontFamily: "var(--font-display)" }}
        >
          Concordance on held-out HSP studies
        </h1>
        <p className="mt-2 text-[15px] leading-relaxed text-[var(--color-fog-400)]">
          Compare CAISR automated scoring against clinical human annotations on unseen HSP
          recordings: staging agreement (Cohen&apos;s κ), per-stage / arousal discrimination
          (AUROC / AUPRC), and AHI agreement.
        </p>
      </div>

      {error && (
        <div className="panel p-6 text-sm text-[var(--color-fog-300)]">
          <div className="mb-2 text-[var(--color-sev-mild)]">No concordance report available yet.</div>
          <p className="text-[var(--color-fog-400)]">
            Generate one by running the evaluator against held-out HSP sites:
          </p>
          <pre className="mt-3 overflow-x-auto rounded border hairline bg-[var(--color-muted)] px-4 py-3 font-mono text-xs text-[var(--color-fog-200)]">
            python scripts/evaluate_concordance.py --n 12 --cohorts I0002 I0003 I0006
          </pre>
          <div className="mt-3 text-xs text-[var(--color-fog-600)]">{error}</div>
        </div>
      )}

      {report && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Chip tone="teal">{report.n_sessions} held-out sessions</Chip>
            {report.cohorts.map((c) => (
              <Chip key={c}>{c}</Chip>
            ))}
          </div>

          <section className="panel p-6">
            <SectionTitle kicker="Sleep staging">Epoch-by-epoch agreement</SectionTitle>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatCard label="Accuracy" value={fmt(report.staging.accuracy)} accent="var(--color-teal)" />
              <StatCard label="Cohen's κ" value={fmt(report.staging.cohen_kappa)} accent="var(--color-teal)" />
              <StatCard label="Macro AUROC" value={fmt(report.staging.macro_auroc)} />
              <StatCard label="Macro AUPRC" value={fmt(report.staging.macro_auprc)} />
            </div>

            <div className="mt-6 grid gap-6 lg:grid-cols-2">
              <div>
                <div className="mb-2 text-[11px] uppercase tracking-[0.14em] text-[var(--color-fog-500)]">
                  Per-stage discrimination
                </div>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[11px] uppercase tracking-wide text-[var(--color-fog-500)]">
                      <th className="py-1.5">Stage</th>
                      <th className="py-1.5">AUROC</th>
                      <th className="py-1.5">AUPRC</th>
                      <th className="py-1.5">Prevalence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.staging.labels.map((lbl) => {
                      const pc = report.staging.per_class[lbl];
                      return (
                        <tr key={lbl} className="border-t hairline">
                          <td className="py-1.5 font-mono text-[var(--color-fog-100)]">{lbl}</td>
                          <td className="py-1.5 text-[var(--color-fog-200)]">{fmt(pc?.auroc)}</td>
                          <td className="py-1.5 text-[var(--color-fog-200)]">{fmt(pc?.auprc)}</td>
                          <td className="py-1.5 text-[var(--color-fog-400)]">{fmt(pc?.prevalence)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div>
                <div className="mb-2 text-[11px] uppercase tracking-[0.14em] text-[var(--color-fog-500)]">
                  Confusion matrix · rows = human, cols = CAISR
                </div>
                <ConfusionMatrix labels={report.staging.labels} matrix={report.staging.confusion_matrix} />
              </div>
            </div>
          </section>

          <div className="grid gap-6 lg:grid-cols-2">
            <section className="panel p-6">
              <SectionTitle kicker="Arousals">Detection (per second)</SectionTitle>
              <div className="grid grid-cols-2 gap-3">
                <StatCard label="AUROC" value={fmt(report.arousal.auroc)} accent="var(--color-cyan)" />
                <StatCard label="AUPRC" value={fmt(report.arousal.auprc)} accent="var(--color-cyan)" />
                <StatCard
                  label="Positive rate"
                  value={fmt(report.arousal.positive_rate)}
                  sub={`${report.arousal.n_seconds.toLocaleString()} s pooled`}
                />
              </div>
              <p className="mt-3 text-xs leading-relaxed text-[var(--color-fog-500)]">
                Arousals are rare (low positive rate), so AUPRC is bounded by prevalence; AUROC reflects
                ranking quality of <span className="font-mono">caisr_prob_arousal</span> against human
                arousal marks.
              </p>
            </section>

            <section className="panel p-6">
              <SectionTitle kicker="Respiratory">AHI agreement</SectionTitle>
              <div className="grid grid-cols-2 gap-3">
                <StatCard
                  label="Bias (human − CAISR)"
                  value={fmt(report.ahi_agreement.bias, 2)}
                  unit="/h"
                  accent="var(--color-teal)"
                />
                <StatCard label="Pearson r" value={fmt(report.ahi_agreement.pearson_r, 3)} />
                <StatCard label="MAE" value={fmt(report.ahi_agreement.mae, 2)} unit="/h" />
                <StatCard
                  label="95% limits of agreement"
                  value={`${fmt(report.ahi_agreement.loa_lower, 1)} … ${fmt(report.ahi_agreement.loa_upper, 1)}`}
                />
              </div>
              <div className="mt-5">
                <BlandAltmanChart agreement={report.ahi_agreement} sessions={report.per_session} />
              </div>
            </section>
          </div>

          {report.by_cohort && Object.keys(report.by_cohort).length > 0 && (
            <section className="panel p-6">
              <SectionTitle kicker="By site">Held-out HSP cohorts</SectionTitle>
              <div className="mt-3 grid gap-3 sm:grid-cols-3">
                {Object.entries(report.by_cohort).map(([c, v]) => (
                  <div key={c} className="panel-quiet px-4 py-3">
                    <div className="font-mono text-sm text-[var(--color-fog-100)]">{c}</div>
                    <div className="mt-1 text-[12px] text-[var(--color-fog-500)]">{v.n} sessions</div>
                    <div className="mt-2 flex gap-4 text-sm">
                      <div>
                        <div className="text-[10px] uppercase text-[var(--color-fog-500)]">κ</div>
                        <div className="font-mono text-[var(--color-fog-200)]">{fmt(v.mean_kappa)}</div>
                      </div>
                      <div>
                        <div className="text-[10px] uppercase text-[var(--color-fog-500)]">Acc</div>
                        <div className="font-mono text-[var(--color-fog-200)]">{fmt(v.mean_accuracy)}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="panel p-6">
            <SectionTitle kicker="Per study">Session breakdown</SectionTitle>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-[var(--color-fog-500)]">
                  <th className="py-1.5">Study</th>
                  <th className="py-1.5">Cohort</th>
                  <th className="py-1.5">Epochs</th>
                  <th className="py-1.5">Accuracy</th>
                  <th className="py-1.5">κ</th>
                  <th className="py-1.5">Human AHI</th>
                  <th className="py-1.5">CAISR AHI</th>
                </tr>
              </thead>
              <tbody>
                {report.per_session.map((s) => (
                  <tr key={s.uid} className="border-t hairline">
                    <td className="py-1.5 font-mono text-[12px] text-[var(--color-fog-200)]">
                      <Link href={`/study/${encodeURIComponent(s.uid)}`} className="hover:text-[var(--color-teal)]">
                        {s.uid}
                      </Link>
                    </td>
                    <td className="py-1.5 text-[var(--color-fog-400)]">{s.cohort}</td>
                    <td className="py-1.5 text-[var(--color-fog-400)]">{s.n_epochs}</td>
                    <td className="py-1.5 text-[var(--color-fog-200)]">{fmt(s.staging_accuracy)}</td>
                    <td className="py-1.5 text-[var(--color-fog-200)]">{fmt(s.staging_kappa)}</td>
                    <td className="py-1.5 text-[var(--color-fog-400)]">{fmt(s.human_ahi, 1)}</td>
                    <td className="py-1.5 text-[var(--color-fog-400)]">{fmt(s.caisr_ahi, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}

function ConfusionMatrix({ labels, matrix }: { labels: string[]; matrix: number[][] }) {
  const max = Math.max(1, ...matrix.flat());
  return (
    <table className="w-full text-center text-xs">
      <thead>
        <tr className="text-[var(--color-fog-500)]">
          <th className="py-1" />
          {labels.map((l) => (
            <th key={l} className="py-1 font-mono">
              {l}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {matrix.map((row, i) => (
          <tr key={labels[i]}>
            <td className="py-1 pr-2 text-right font-mono text-[var(--color-fog-500)]">{labels[i]}</td>
            {row.map((v, j) => {
              const t = v / max;
              const diag = i === j;
              return (
                <td
                  key={j}
                  className="py-1"
                  style={{
                    background: diag
                      ? `color-mix(in srgb, var(--color-teal) ${Math.round(t * 70)}%, transparent)`
                      : `color-mix(in srgb, var(--color-sev-mild) ${Math.round(t * 60)}%, transparent)`,
                    color: t > 0.4 ? "var(--color-ink-900)" : "var(--color-fog-300)",
                  }}
                >
                  {v}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
