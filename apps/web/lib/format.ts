import type { Severity } from "./types";

export function fmt(value: number | null | undefined, digits = 1, dash = "—"): string {
  if (value === null || value === undefined || Number.isNaN(value)) return dash;
  return value.toFixed(digits);
}

export function fmtInt(value: number | null | undefined, dash = "—"): string {
  if (value === null || value === undefined || Number.isNaN(value)) return dash;
  return Math.round(value).toString();
}

export function minutesToHms(min: number | null | undefined): string {
  if (min === null || min === undefined || Number.isNaN(min)) return "—";
  const total = Math.round(min * 60);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  return `${h}h ${m.toString().padStart(2, "0")}m`;
}

export const severityColor: Record<Severity, string> = {
  normal: "var(--color-sev-normal)",
  mild: "var(--color-sev-mild)",
  moderate: "var(--color-sev-moderate)",
  severe: "var(--color-sev-severe)",
  unknown: "var(--color-fog-500)",
};

export const stageColor: Record<string, string> = {
  W: "var(--color-stage-wake)",
  REM: "var(--color-stage-rem)",
  N1: "var(--color-stage-n1)",
  N2: "var(--color-stage-n2)",
  N3: "var(--color-stage-n3)",
  "?": "var(--color-stage-unknown)",
};

export const eventColor: Record<string, string> = {
  apnea_obstructive: "#ff6b6b",
  apnea_central: "#ff9e64",
  apnea_mixed: "#ff8ab0",
  hypopnea: "#f2c14e",
  rera: "#c3e88d",
  arousal: "#52b8ff",
  limb_movement: "#8b7bff",
  desaturation: "#37d39a",
  position: "#64769c",
};

export const eventLabel: Record<string, string> = {
  apnea_obstructive: "Obstructive apnea",
  apnea_central: "Central apnea",
  apnea_mixed: "Mixed apnea",
  hypopnea: "Hypopnea",
  rera: "RERA",
  arousal: "Arousal",
  limb_movement: "Limb movement",
  desaturation: "Desaturation",
  position: "Position",
};

export function prettyStudyType(t: string): string {
  const map: Record<string, string> = {
    diagnostic: "Diagnostic",
    split_night: "Split-night",
    titration: "PAP titration",
    mslt: "MSLT",
    mwt: "MWT",
    hsat: "Home test",
    other: "Other",
    unknown: "Unclassified",
  };
  return map[t] ?? t;
}

export function ageLabel(age: number | null | undefined, population: string): string {
  if (age === null || age === undefined) return "Age n/a";
  if (population === "pediatric" || age < 18) {
    return age < 2 ? `${(age * 12).toFixed(0)} mo` : `${Math.round(age)} yr (peds)`;
  }
  return `${Math.round(age)} yr`;
}
