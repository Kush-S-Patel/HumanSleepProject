"""Build a patient-level session registry from the per-cohort metadata CSVs."""

from __future__ import annotations

import csv
import glob
import os
from typing import Optional

from .paths import patient_uid, session_uid

# Cohort -> population type (drives pediatric vs adult interpretation).
COHORT_POPULATION = {
    "S0001": "adult",
    "I0002": "adult",
    "I0003": "pediatric",
    "I0004": "adult",
    "I0006": "adult",
    "I0007": "adult",
}


def normalize_study_type(raw: Optional[str], raw_name: Optional[str] = None) -> str:
    """Collapse free-text study type into a normalized category."""
    text = f"{raw or ''} {raw_name or ''}".strip().lower()
    if not text:
        return "unknown"
    if "split" in text:
        return "split_night"
    if any(k in text for k in ("cpap", "bipap", "bilevel", "titration", "pap")):
        return "titration"
    if "mslt" in text:
        return "mslt"
    if "mwt" in text:
        return "mwt"
    if "diagnostic" in text:
        return "diagnostic"
    if text.startswith("psg") or "polysom" in text:
        return "diagnostic"
    if "hsat" in text or "home sleep" in text:
        return "hsat"
    return "other"


def _as_bool(value: Optional[str]) -> bool:
    return str(value or "").strip().upper() in ("Y", "YES", "TRUE", "1")


def _as_float(value: Optional[str]) -> Optional[float]:
    try:
        v = float(str(value).strip())
        return v
    except (TypeError, ValueError):
        return None


def _ci_lookup(row: dict) -> dict:
    """Return a case-insensitive view of a CSV row."""
    return {str(k).strip().lower(): v for k, v in row.items() if k is not None}


def _first(ci: dict, *keys: str) -> Optional[str]:
    for k in keys:
        v = ci.get(k.lower())
        if v is not None and str(v).strip() != "":
            return v
    return None


def parse_session_row(row: dict) -> Optional[dict]:
    # Column naming varies across cohorts (e.g. BidsFolder vs BIDSFolder,
    # HasSleepAnnotations vs SleepAnnotations vs HasAnnotations), so look up
    # every field through a case-insensitive, multi-alias getter.
    ci = _ci_lookup(row)
    site = (_first(ci, "SiteID") or "").strip()
    patient = (_first(ci, "BDSPPatientID") or "").strip()
    session = (_first(ci, "SessionID") or "").strip()
    bids_folder = (_first(ci, "BidsFolder", "BIDSFolder") or "").strip()
    if not (site and patient and session and bids_folder):
        return None

    age = _as_float(_first(ci, "AgeAtVisit"))
    age_days = _as_float(_first(ci, "AgeInDaysAtVisit"))
    if (age is None or age == 0) and age_days is not None:
        age = round(age_days / 365.25, 2)

    study_type = normalize_study_type(_first(ci, "StudyType"), _first(ci, "StudyTypeName"))
    population = COHORT_POPULATION.get(site, "adult")

    has_staging = _as_bool(_first(ci, "HasStaging"))
    has_sleep = _as_bool(_first(ci, "HasSleepAnnotations", "SleepAnnotations", "HasAnnotations"))
    has_events = _as_bool(_first(ci, "HasEventsAnnotations", "EventAnnotations", "HasAnnotations"))
    creation = (_first(ci, "CreationTime", "StartDateTime") or "").strip() or None

    return {
        "uid": session_uid(site, patient, session),
        "patient_uid": patient_uid(site, patient),
        "cohort": site,
        "patient_id": patient,
        "session_id": session,
        "bids_folder": bids_folder,
        "creation_time": creation,
        "age": age,
        "sex": (_first(ci, "SexDSC", "Sex") or "").strip() or None,
        "population": population,
        "study_type": study_type,
        "study_type_raw": (_first(ci, "StudyType") or "").strip() or None,
        "has_staging": has_staging,
        "has_sleep_annotations": has_sleep,
        "has_events_annotations": has_events,
        # Quality columns exist in newer metadata releases; tolerate absence.
        "likert_scale": (_first(ci, "likert_scale") or "").strip() or None,
        "quality_score": _as_float(_first(ci, "quality_score")),
        "caisr_training_set": _as_bool(_first(ci, "caisr_training_set"))
        if _first(ci, "caisr_training_set") is not None
        else None,
    }


def read_metadata_csv(path: str) -> list[dict]:
    sessions: list[dict] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            parsed = parse_session_row(row)
            if parsed is not None:
                sessions.append(parsed)
    return sessions


def build_registry(metadata_dir: str) -> dict:
    """Read all ``*_psg_metadata_*.csv`` files under ``metadata_dir``.

    Returns a dict with ``sessions`` (list) and ``patients`` (list of grouped
    patient records) plus ``cohorts`` summary counts.
    """
    files = sorted(glob.glob(os.path.join(metadata_dir, "*.csv")))
    sessions: list[dict] = []
    for path in files:
        try:
            sessions.extend(read_metadata_csv(path))
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[registry] skipping {path}: {exc}")

    patients: dict[str, dict] = {}
    for s in sessions:
        p = patients.setdefault(
            s["patient_uid"],
            {
                "patient_uid": s["patient_uid"],
                "cohort": s["cohort"],
                "patient_id": s["patient_id"],
                "population": s["population"],
                "sessions": [],
            },
        )
        p["sessions"].append(s["uid"])

    for p in patients.values():
        p["n_sessions"] = len(p["sessions"])

    cohorts: dict[str, dict] = {}
    for s in sessions:
        c = cohorts.setdefault(
            s["cohort"],
            {"cohort": s["cohort"], "population": s["population"], "n_sessions": 0, "n_patients": 0},
        )
        c["n_sessions"] += 1
    for p in patients.values():
        cohorts[p["cohort"]]["n_patients"] += 1

    return {
        "sessions": sessions,
        "patients": list(patients.values()),
        "cohorts": list(cohorts.values()),
        "n_sessions": len(sessions),
        "n_patients": len(patients),
    }
