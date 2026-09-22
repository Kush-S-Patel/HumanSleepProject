"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { fetchCohorts, fetchWorklist } from "@/lib/api";
import type { Cohort, WorklistItem } from "@/lib/types";
import { ageLabel, fmt, prettyStudyType, severityColor } from "@/lib/format";
import { Chip, SeverityBadge } from "./components/ui";

const REVIEW_LABEL: Record<string, string> = {
  pending_review: "Pending",
  in_review: "In review",
  reviewed: "Reviewed",
  signed_off: "Signed off",
};

export default function WorklistPage() {
  const [cohorts, setCohorts] = useState<Cohort[]>([]);
  const [items, setItems] = useState<WorklistItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [cohort, setCohort] = useState<string>("");
  const [population, setPopulation] = useState<string>("");
  const [studyType, setStudyType] = useState<string>("");
  const [cachedOnly, setCachedOnly] = useState(true);
  const [reviewStatus, setReviewStatus] = useState<string>("");
  const [severity, setSeverity] = useState<string>("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetchCohorts()
      .then((d) => setCohorts(d.cohorts))
      .catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    const t = setTimeout(() => {
      fetchWorklist({
        cohort: cohort || undefined,
        population: population || undefined,
        study_type: studyType || undefined,
        cached_only: cachedOnly,
        search: search || undefined,
        review_status: reviewStatus || undefined,
        severity: severity || undefined,
        limit: 150,
      })
        .then((d) => {
          setItems(d.items);
          setTotal(d.total);
        })
        .catch(() => setItems([]))
        .finally(() => setLoading(false));
    }, 180);
    return () => clearTimeout(t);
  }, [cohort, population, studyType, cachedOnly, search, reviewStatus, severity]);

  const totalSessions = useMemo(
    () => cohorts.reduce((s, c) => s + c.n_sessions, 0),
    [cohorts],
  );
  const totalPatients = useMemo(
    () => cohorts.reduce((s, c) => s + c.n_patients, 0),
    [cohorts],
  );
  const pendingCount = useMemo(
    () => items.filter((i) => i.review_status === "pending_review" || i.review_status === "in_review").length,
    [items],
  );

  return (
    <div className="space-y-7">
      <section className="animate-rise">
        <div className="text-[12px] text-[var(--color-fog-500)]">Clinic triage · Human Sleep Project</div>
        <h1
          className="font-display mt-1.5 max-w-3xl text-[1.85rem] leading-snug text-[var(--color-fog-100)]"
          style={{ fontFamily: "var(--font-display)" }}
        >
          Overnight studies ready for review
        </h1>
        <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-[var(--color-fog-400)]">
          Triage AI-scored and human-annotated PSGs by OSA severity, open a report, run epoch QC, then
          sign off and export a clinician PDF. Decision support — not a diagnosis.
        </p>
      </section>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
        <OverviewTile label="Patients" value={totalPatients.toLocaleString()} accent />
        <OverviewTile label="Recordings" value={totalSessions.toLocaleString()} accent />
        <OverviewTile label="On this page" value={String(items.length)} sub={`${pendingCount} need review`} />
        {cohorts
          .slice()
          .sort((a, b) => a.cohort.localeCompare(b.cohort))
          .slice(0, 3)
          .map((c) => (
            <OverviewTile
              key={c.cohort}
              label={`${c.cohort} · ${c.population === "pediatric" ? "Peds" : "Adult"}`}
              value={c.n_patients.toLocaleString()}
              sub={`${c.n_sessions.toLocaleString()} studies`}
            />
          ))}
      </section>

      <section className="panel p-4">
        <div className="flex flex-wrap items-center gap-3">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search patient / study ID…"
            className="field-input min-w-[220px] flex-1"
          />
          <Select
            value={reviewStatus}
            onChange={setReviewStatus}
            label="Review"
            options={[
              ["", "All review states"],
              ["pending_review", "Pending"],
              ["in_review", "In review"],
              ["reviewed", "Reviewed"],
              ["signed_off", "Signed off"],
            ]}
          />
          <Select
            value={severity}
            onChange={setSeverity}
            label="OSA severity"
            options={[
              ["", "All severities"],
              ["normal", "Normal"],
              ["mild", "Mild"],
              ["moderate", "Moderate"],
              ["severe", "Severe"],
            ]}
          />
          <Select
            value={cohort}
            onChange={setCohort}
            label="Cohort"
            options={[["", "All cohorts"], ...cohorts.map((c) => [c.cohort, c.cohort] as [string, string])]}
          />
          <Select
            value={population}
            onChange={setPopulation}
            label="Population"
            options={[
              ["", "All ages"],
              ["adult", "Adult"],
              ["pediatric", "Pediatric"],
            ]}
          />
          <Select
            value={studyType}
            onChange={setStudyType}
            label="Study type"
            options={[
              ["", "All types"],
              ["diagnostic", "Diagnostic"],
              ["split_night", "Split-night"],
              ["titration", "PAP titration"],
              ["mslt", "MSLT"],
            ]}
          />
          <label className="flex items-center gap-2 text-sm text-[var(--color-fog-300)]">
            <input
              type="checkbox"
              checked={cachedOnly}
              onChange={(e) => setCachedOnly(e.target.checked)}
              className="h-4 w-4 accent-[var(--color-teal)]"
            />
            Analyzed only
          </label>
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <div className="text-sm text-[var(--color-fog-400)]">
            {loading ? "Loading…" : `${items.length} shown`}
            {!cachedOnly && total > items.length ? ` of ${total.toLocaleString()}` : ""}
          </div>
        </div>
        <div className="panel overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b hairline bg-[var(--color-muted)]/50 text-left text-[11px] uppercase tracking-wide text-[var(--color-fog-500)]">
                <th className="px-4 py-3 font-medium">Study</th>
                <th className="px-4 py-3 font-medium">AHI</th>
                <th className="px-4 py-3 font-medium">OSA</th>
                <th className="px-4 py-3 font-medium">Type</th>
                <th className="px-4 py-3 font-medium">Source</th>
                <th className="px-4 py-3 font-medium">Review</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr
                  key={it.uid}
                  className="border-b border-[var(--color-line)] transition-colors hover:bg-[var(--color-muted)]/40"
                >
                  <td className="px-4 py-3">
                    <div className="font-medium text-[var(--color-fog-100)]">
                      {it.display_name || it.uid}
                    </div>
                    <div className="font-mono text-[11px] text-[var(--color-fog-500)]">
                      {it.cohort} · {ageLabel(it.age, it.population)}
                      {it.sex ? ` · ${it.sex[0]}` : ""}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className="stat-value text-[16px]"
                      style={{
                        color:
                          it.osa_severity && it.osa_severity !== "unknown"
                            ? severityColor[it.osa_severity]
                            : "var(--color-fog-200)",
                      }}
                    >
                      {it.cached ? fmt(it.ahi ?? null, 1) : "—"}
                    </span>
                    {it.cached && <span className="text-[11px] text-[var(--color-fog-500)]"> /h</span>}
                  </td>
                  <td className="px-4 py-3">
                    {it.osa_severity ? (
                      <SeverityBadge severity={it.osa_severity} />
                    ) : (
                      <span className="text-[var(--color-fog-500)]">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-[var(--color-fog-300)]">{prettyStudyType(it.study_type)}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {it.annotation_source === "caisr" && <Chip tone="teal">CAISR</Chip>}
                      {it.annotation_source === "human" && <Chip>Human</Chip>}
                      {it.synthetic && <Chip tone="teal">Demo</Chip>}
                      {!it.annotation_source && it.has_staging && <Chip tone="muted">Staged</Chip>}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-[13px] text-[var(--color-fog-300)]">
                    {it.cached
                      ? REVIEW_LABEL[it.review_status || "pending_review"] || it.review_status
                      : "Not analyzed"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {it.cached ? (
                      <Link href={`/study/${encodeURIComponent(it.uid)}`} className="btn-primary">
                        Open
                      </Link>
                    ) : (
                      <span className="text-[12px] text-[var(--color-fog-500)]">—</span>
                    )}
                  </td>
                </tr>
              ))}
              {!loading && items.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-[var(--color-fog-500)]">
                    No studies match these filters.
                    {cachedOnly &&
                      " Try unchecking ‘Analyzed only’, or build cache / sample data."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function OverviewTile({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div className="panel-quiet px-4 py-3">
      <div className="text-[10px] uppercase tracking-[0.08em] text-[var(--color-fog-500)]">{label}</div>
      <div
        className="stat-value mt-1 text-[22px]"
        style={{ color: accent ? "var(--color-teal)" : "var(--color-fog-100)" }}
      >
        {value}
      </div>
      {sub && <div className="text-[11px] text-[var(--color-fog-500)]">{sub}</div>}
    </div>
  );
}

function Select({
  value,
  onChange,
  label,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  label: string;
  options: [string, string][];
}) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="field-input w-auto"
    >
      {options.map(([v, l]) => (
        <option key={v} value={v}>
          {l}
        </option>
      ))}
    </select>
  );
}
