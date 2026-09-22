import type {
  Cohort,
  ConcordanceReport,
  EpochWindow,
  Hypnogram,
  Job,
  ScoredEvent,
  Signals,
  StudyComparison,
  StudyReport,
  Worklist,
} from "./types";

const BASE = ""; // same-origin; Next rewrites /api -> FastAPI

// Large multipart uploads (EDF/H5) must bypass the Next rewrite proxy, whose
// request-body buffer is capped at 10MB in Next 15 (truncation -> HTTP 500).
// They are sent straight to the FastAPI backend, which has CORS enabled.
const UPLOAD_ORIGIN =
  process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://127.0.0.1:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${detail ? ` — ${detail}` : ""}`);
  }
  return res.json() as Promise<T>;
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${detail ? ` — ${detail}` : ""}`);
  }
  return res.json() as Promise<T>;
}

export interface WorklistQuery {
  cohort?: string;
  population?: string;
  study_type?: string;
  cached_only?: boolean;
  search?: string;
  review_status?: string;
  severity?: string;
  limit?: number;
  offset?: number;
}

export function fetchWorklist(q: WorklistQuery = {}): Promise<Worklist> {
  const params = new URLSearchParams();
  if (q.cohort) params.set("cohort", q.cohort);
  if (q.population) params.set("population", q.population);
  if (q.study_type) params.set("study_type", q.study_type);
  if (q.cached_only) params.set("cached_only", "true");
  if (q.search) params.set("search", q.search);
  if (q.review_status) params.set("review_status", q.review_status);
  if (q.severity) params.set("severity", q.severity);
  params.set("limit", String(q.limit ?? 100));
  params.set("offset", String(q.offset ?? 0));
  return get<Worklist>(`/api/worklist?${params.toString()}`);
}

export function fetchCohorts(): Promise<{ cohorts: Cohort[] }> {
  return get(`/api/cohorts`);
}

export function fetchStudy(uid: string): Promise<StudyReport> {
  return get<StudyReport>(`/api/studies/${encodeURIComponent(uid)}`);
}

export function fetchHypnogram(uid: string): Promise<Hypnogram> {
  return get<Hypnogram>(`/api/studies/${encodeURIComponent(uid)}/hypnogram`);
}

export function fetchEvents(uid: string): Promise<{ events: ScoredEvent[] }> {
  return get(`/api/studies/${encodeURIComponent(uid)}/events`);
}

export function fetchSignals(uid: string): Promise<Signals> {
  return get<Signals>(`/api/studies/${encodeURIComponent(uid)}/signals`);
}

export function fetchComparison(uid: string): Promise<StudyComparison> {
  return get(`/api/studies/${encodeURIComponent(uid)}/comparison`);
}

export function fetchEpochWindow(uid: string, epochIndex: number): Promise<EpochWindow> {
  return get(`/api/studies/${encodeURIComponent(uid)}/epoch/${epochIndex}`);
}

export function overrideStage(uid: string, epochIndex: number, stage: string) {
  return patch(`/api/studies/${encodeURIComponent(uid)}/hypnogram`, {
    epoch_index: epochIndex,
    stage,
  });
}

export function overrideEvent(
  uid: string,
  body: {
    action: "set" | "add" | "delete";
    index?: number;
    event?: ScoredEvent;
    events?: ScoredEvent[];
  },
) {
  return patch(`/api/studies/${encodeURIComponent(uid)}/events`, body);
}

export function exportUrl(uid: string, kind: "json" | "bids.tsv" | "html" | "pdf"): string {
  return `/api/studies/${encodeURIComponent(uid)}/export.${kind}`;
}

export function fetchReview(uid: string): Promise<import("./types").ReviewState> {
  return get(`/api/studies/${encodeURIComponent(uid)}/review`);
}

export function updateReview(
  uid: string,
  body: { status: string; reviewer?: string; notes?: string },
) {
  return patch(`/api/studies/${encodeURIComponent(uid)}/review`, body);
}

export function fetchJob(id: string): Promise<Job> {
  return get<Job>(`/api/jobs/${encodeURIComponent(id)}`);
}

export function fetchConcordance(): Promise<ConcordanceReport> {
  return get<ConcordanceReport>(`/api/eval/concordance`);
}

export async function uploadStudy(form: FormData): Promise<Job> {
  const res = await fetch(`${UPLOAD_ORIGIN}/api/uploads`, { method: "POST", body: form });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${detail ? ` — ${detail}` : ""}`);
  }
  return res.json();
}
