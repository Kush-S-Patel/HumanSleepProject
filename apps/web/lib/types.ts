export type Severity = "normal" | "mild" | "moderate" | "severe" | "unknown";

export type ReviewStatus = "pending_review" | "in_review" | "reviewed" | "signed_off";

export interface ReviewState {
  status: ReviewStatus;
  reviewer: string | null;
  notes: string | null;
  updated_at: string | null;
  history?: { status: string; reviewer?: string | null; notes?: string | null; at: string }[];
}

export interface WorklistItem {
  uid: string;
  patient_uid: string;
  cohort: string;
  population: string;
  age: number | null;
  sex: string | null;
  study_type: string;
  creation_time: string | null;
  has_staging: boolean;
  has_events_annotations: boolean;
  likert_scale: string | null;
  cached: boolean;
  synthetic?: boolean;
  display_name?: string | null;
  ahi?: number | null;
  osa_severity?: Severity | null;
  overall_severity?: Severity | null;
  review_status?: ReviewStatus | null;
  annotation_source?: string | null;
}

export interface Worklist {
  total: number;
  count: number;
  offset: number;
  items: WorklistItem[];
}

export interface Cohort {
  cohort: string;
  population: string;
  n_sessions: number;
  n_patients: number;
}

export interface StudyMeta {
  uid: string;
  patient_uid: string;
  cohort: string;
  population: string;
  age: number | null;
  sex: string | null;
  display_name?: string;
  study_type: string;
  study_type_raw?: string;
  creation_time: string | null;
  annotation_source: string;
  has_staging: boolean;
  has_events: boolean;
  n_events: number;
  start_clock: string | null;
  synthetic?: boolean;
  uploaded?: boolean;
  provenance?: {
    scorer?: string;
    caisr_images?: string[];
    psg_core_version?: string;
    pipeline?: string;
    source_filename?: string;
    sanitized?: boolean;
    sanitize_steps?: string[];
    spo2_from_waveform?: boolean;
    combine_fallback?: boolean;
    created_at?: string;
  };
  review?: ReviewState;
}

export interface Metrics {
  epoch_length_sec: number;
  n_epochs: number;
  n_scored_epochs: number;
  time_in_bed_min: number | null;
  total_sleep_time_min: number | null;
  sleep_period_time_min: number | null;
  waso_min: number | null;
  sleep_latency_min: number | null;
  rem_latency_min: number | null;
  sleep_efficiency_pct: number | null;
  wake_min: number | null;
  n1_min: number | null;
  n2_min: number | null;
  n3_min: number | null;
  rem_min: number | null;
  n1_pct: number | null;
  n2_pct: number | null;
  n3_pct: number | null;
  rem_pct: number | null;
  sleep_fragmentation_index: number | null;
  arousal_index: number | null;
  n_arousals: number;
  ahi: number | null;
  rdi: number | null;
  apnea_index: number | null;
  obstructive_apnea_index: number | null;
  central_apnea_index: number | null;
  hypopnea_index: number | null;
  n_obstructive_apnea: number;
  n_central_apnea: number;
  n_mixed_apnea: number;
  n_hypopnea: number;
  n_rera: number;
  spo2_nadir: number | null;
  odi: number | null;
  n_desaturations: number;
  plm_index: number | null;
  n_limb_movements: number;
}

export interface Finding {
  domain: string;
  severity: Severity;
  title: string;
  detail: string;
}

export interface Summary {
  population: string;
  osa_severity: Severity;
  overall_severity: Severity;
  headline: string;
  findings: Finding[];
  caveats: string[];
  disclaimer: string;
}

export interface StudyReport {
  meta: StudyMeta;
  metrics: Metrics;
  summary: Summary;
}

export interface Hypnogram {
  epoch_length_sec: number;
  start_clock: string | null;
  stages: string[];
  source: string;
}

export interface ScoredEvent {
  onset_sec: number;
  duration_sec: number;
  category: string;
  subtype: string;
  nadir_spo2: number | null;
}

export interface Signals {
  fs: number;
  channels: Record<string, number[]>;
  synthetic?: boolean;
}

export interface Job {
  id: string;
  filename: string;
  status: "queued" | "running" | "done" | "failed" | "needs_setup";
  progress: number;
  message: string;
  study_uid: string | null;
}

export interface StageClassMetric {
  auroc: number | null;
  auprc: number | null;
  prevalence: number | null;
}

export interface StagingConcordance {
  n_epochs: number;
  accuracy: number | null;
  cohen_kappa: number | null;
  labels: string[];
  confusion_matrix: number[][];
  macro_auroc: number | null;
  macro_auprc: number | null;
  per_class: Record<string, StageClassMetric>;
}

export interface ArousalConcordance {
  n_seconds: number;
  positive_rate: number | null;
  auroc: number | null;
  auprc: number | null;
}

export interface AhiAgreement {
  n: number;
  bias?: number;
  sd?: number;
  loa_lower?: number;
  loa_upper?: number;
  mae?: number;
  pearson_r?: number | null;
  points?: {
    uid: string;
    cohort?: string;
    human: number;
    caisr: number;
    mean: number;
    diff: number;
  }[];
}

export interface CohortConcordance {
  n: number;
  mean_kappa: number | null;
  mean_accuracy: number | null;
}

export interface ConcordanceSession {
  uid: string;
  cohort: string;
  n_epochs: number;
  staging_accuracy: number | null;
  staging_kappa: number | null;
  human_ahi: number | null;
  caisr_ahi: number | null;
}

export interface ConcordanceReport {
  n_sessions: number;
  cohorts: string[];
  staging: StagingConcordance;
  arousal: ArousalConcordance;
  ahi_agreement: AhiAgreement;
  by_cohort?: Record<string, CohortConcordance>;
  per_session: ConcordanceSession[];
}

export interface StudyComparison {
  source?: string;
  uid?: string;
  human: Record<string, number | null | undefined>;
  ai: Record<string, number | null | undefined>;
  n_epochs?: number;
  cohort?: string;
}

export interface EpochWindow {
  epoch_index: number;
  stage: string;
  epoch_length_sec: number;
  window_start_sec: number;
  window_end_sec: number;
  fs: number;
  traces: Record<string, number[]>;
  events: ScoredEvent[];
  stages_nearby: string[];
}
