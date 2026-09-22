"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { fetchJob, uploadStudy } from "@/lib/api";
import type { Job } from "@/lib/types";
import { SectionTitle } from "@/app/components/ui";

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [population, setPopulation] = useState("adult");
  const [age, setAge] = useState("");
  const [sex, setSex] = useState("");
  const [studyType, setStudyType] = useState("diagnostic");
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const startPolling = (id: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const j = await fetchJob(id);
        setJob(j);
        if (["done", "failed", "needs_setup"].includes(j.status) && pollRef.current) {
          clearInterval(pollRef.current);
        }
      } catch {
        /* keep polling */
      }
    }, 1200);
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setJob(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("population", population);
      if (age) fd.append("age", age);
      if (sex) fd.append("sex", sex);
      fd.append("study_type", studyType);
      fd.append("display_name", file.name);
      const j = await uploadStudy(fd);
      setJob(j);
      startPolling(j.id);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="animate-rise">
        <div className="text-[12px] text-[var(--color-fog-500)]">Upload · CAISR / annotations</div>
        <h1
          className="font-display mt-1.5 text-[1.75rem] leading-snug text-[var(--color-fog-100)]"
          style={{ fontFamily: "var(--font-display)" }}
        >
          Score a recording with HSP tooling
        </h1>
        <p className="mt-2 text-[15px] leading-relaxed text-[var(--color-fog-400)]">
          Upload an HSP annotation <span className="font-mono text-[var(--color-fog-300)]">.csv</span> for
          an immediate report from human scores, or a raw{" "}
          <span className="font-mono text-[var(--color-fog-300)]">.edf</span> /{" "}
          <span className="font-mono text-[var(--color-fog-300)]">.h5</span> file to run the CAISR
          automated pipeline used on this dataset.
        </p>
      </div>

      <form onSubmit={onSubmit} className="panel space-y-5 p-6">
        <label className="block cursor-pointer rounded-lg border border-dashed border-[var(--color-line)] bg-[var(--color-muted)]/40 px-6 py-10 text-center transition-colors hover:bg-[var(--color-muted)]/70">
          <input
            type="file"
            accept=".csv,.edf,.h5"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          {file ? (
            <div>
              <div className="font-mono text-sm text-[var(--color-fog-100)]">{file.name}</div>
              <div className="mt-1 text-xs text-[var(--color-fog-500)]">
                {(file.size / 1024 / 1024).toFixed(1)} MB · click to change
              </div>
            </div>
          ) : (
            <div>
              <div className="text-sm text-[var(--color-fog-200)]">Click to choose a file</div>
              <div className="mt-1 text-xs text-[var(--color-fog-500)]">.csv, .edf, or .h5</div>
            </div>
          )}
        </label>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Field label="Population">
            <select
              value={population}
              onChange={(e) => setPopulation(e.target.value)}
              className="field-input"
            >
              <option value="adult">Adult</option>
              <option value="pediatric">Pediatric</option>
            </select>
          </Field>
          <Field label="Age (yr)">
            <input
              value={age}
              onChange={(e) => setAge(e.target.value)}
              inputMode="numeric"
              placeholder="—"
              className="field-input"
            />
          </Field>
          <Field label="Sex">
            <select value={sex} onChange={(e) => setSex(e.target.value)} className="field-input">
              <option value="">—</option>
              <option value="Male">Male</option>
              <option value="Female">Female</option>
            </select>
          </Field>
          <Field label="Study type">
            <select
              value={studyType}
              onChange={(e) => setStudyType(e.target.value)}
              className="field-input"
            >
              <option value="diagnostic">Diagnostic</option>
              <option value="split_night">Split-night</option>
              <option value="titration">PAP titration</option>
            </select>
          </Field>
        </div>

        <button type="submit" disabled={!file || busy} className="btn-primary w-full py-2.5">
          {busy ? "Uploading…" : "Analyze recording"}
        </button>

        {error && <div className="text-sm text-[var(--color-sev-severe)]">{error}</div>}
      </form>

      {job && <JobStatus job={job} />}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-[11px] uppercase tracking-wide text-[var(--color-fog-500)]">{label}</div>
      {children}
    </div>
  );
}

function JobStatus({ job }: { job: Job }) {
  const pct = Math.round((job.progress ?? 0) * 100);
  const tone =
    job.status === "done"
      ? "var(--color-teal)"
      : job.status === "failed"
        ? "var(--color-sev-severe)"
        : job.status === "needs_setup"
          ? "var(--color-sev-mild)"
          : "var(--color-cyan)";

  return (
    <div className="panel p-5">
      <SectionTitle kicker="Analysis job">{job.filename}</SectionTitle>
      <div className="mb-2 h-2 w-full overflow-hidden rounded bg-[var(--color-muted)]">
        <div className="h-full rounded transition-all" style={{ width: `${pct}%`, background: tone }} />
      </div>
      <div className="flex items-center justify-between text-sm">
        <span className="capitalize" style={{ color: tone }}>
          {job.status.replace("_", " ")}
        </span>
        <span className="text-[var(--color-fog-500)]">{pct}%</span>
      </div>
      <div className="mt-2 text-sm text-[var(--color-fog-400)]">{job.message}</div>

      {job.status === "done" && job.study_uid && (
        <Link
          href={`/study/${encodeURIComponent(job.study_uid)}`}
          className="btn-primary mt-4"
        >
          Open report →
        </Link>
      )}
    </div>
  );
}
