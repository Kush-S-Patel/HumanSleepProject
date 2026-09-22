"""Orchestrates the CAISR docker pipeline for raw EDF/H5 uploads.

Design goals:
* Use the real CAISR containers when they are installed.
* Fail *loudly and actionably* (``needs_setup``) when they are not, instead of
  pretending to score a recording.

The CAISR pipeline (github.com/bdsp-core/CAISR-App) runs:
    preprocess (edf->h5) -> stage / arousal / resp / limb -> report
and writes a combined 2 Hz annotation CSV that we convert into our compact
artifact schema via ``psg_core.caisr.parse_caisr_csv``.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Callable, Optional

from psg_core import __version__ as PSG_CORE_VERSION
from psg_core.artifacts import events_to_json, write_study
from psg_core.caisr import parse_caisr_csv
from psg_core.caisr_combine import combine_intermediate
from psg_core.cds import build_clinical_summary
from psg_core.edf import sanitize_edf
from psg_core.edf_signals import pick_spo2, read_edf_channels
from psg_core.hypnogram import build_hypnogram
from psg_core.metrics import compute_metrics
from psg_core.spo2 import apply_spo2_to_metrics, enrich_events_with_spo2

# Docker images expected to be loaded (see docker/README.md).
CAISR_IMAGES = ["caisr_preprocess", "caisr_stage", "caisr_arousal", "caisr_resp", "caisr_limb", "caisr_report"]

SETUP_HELP = (
    "CAISR sleep-AI containers are not installed, so raw EDF/H5 cannot be scored yet. "
    "See docker/README.md: load the CAISR images (docker load) from "
    "github.com/bdsp-core/CAISR-App, then retry. "
    "Tip: you can also upload an HSP annotation .csv to get an immediate report without CAISR."
)


class CaisrError(RuntimeError):
    pass


class CaisrNotAvailable(RuntimeError):
    pass


def _docker_available() -> bool:
    exe = shutil.which("docker")
    if not exe:
        return False
    try:
        subprocess.run(["docker", "info"], check=True, capture_output=True, text=True, timeout=20)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False


def _images_present() -> bool:
    try:
        res = subprocess.run(
            ["docker", "images", "--format", "{{.Repository}}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False
    repos = set(res.stdout.split())
    return any(any(img in r for r in repos) for img in CAISR_IMAGES)


def run_caisr(
    input_path: str,
    *,
    job: dict,
    data_root: str,
    progress_cb: Optional[Callable[[float, str], None]] = None,
) -> str:
    """Run CAISR on an EDF/H5 file and write compact artifacts. Returns study uid."""
    if not _docker_available():
        raise CaisrNotAvailable(SETUP_HELP)
    if not _images_present():
        raise CaisrNotAvailable(SETUP_HELP)

    def report(p: float, msg: str) -> None:
        if progress_cb:
            progress_cb(p, msg)

    work = os.path.join(data_root, "jobs", f"caisr-{job['id']}")
    raw_dir = os.path.join(work, "data", "raw")
    out_dir = os.path.join(work, "caisr_output")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)
    dest = os.path.join(raw_dir, os.path.basename(input_path))

    sanitize_info: dict = {}
    # EDF+ files carry an annotations channel that MNE (used by CAISR preprocess)
    # can choke on; strip it so only signal channels reach the pipeline. H5 files
    # are already in CAISR's expected format and are copied as-is.
    if os.path.splitext(input_path)[1].lower() == ".edf":
        sanitize_info = sanitize_edf(input_path, dest)
    else:
        shutil.copy(input_path, dest)
        sanitize_info = {"steps": ["copied_h5_as_is"], "dropped_annotations": False}

    # app/ -> api/ -> apps/ -> repo root, then docker/run_caisr.py
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    runner = os.path.join(repo_root, "docker", "run_caisr.py")
    report(0.3, "Preprocessing and scoring with CAISR (stage/arousal/resp/limb)")
    try:
        subprocess.run(
            [sys.executable or "python", runner, "--work", work],
            check=True,
            capture_output=True,
            text=True,
            timeout=60 * 60,
        )
    except subprocess.CalledProcessError as exc:
        raise CaisrError(f"CAISR pipeline failed: {exc.stderr.strip()[:400]}")
    except subprocess.TimeoutExpired:
        raise CaisrError("CAISR pipeline timed out")

    report(0.85, "Combining CAISR annotations into report")
    combined = _find_combined_csv(out_dir)
    combine_fallback = False
    if not combined:
        # Upstream report only emits a combined CSV when *all* four tasks wrote
        # a matching file. Limb silently skips EDFs with no leg EMG — common on
        # synthetic/truncated recordings — so rebuild from intermediate CSVs
        # (synthesizing an all-zero limb stream when needed).
        combined = combine_intermediate(out_dir)
        combine_fallback = bool(combined)
    if not combined:
        # Most often preprocess skipped the EDF (missing abd/chest/EOG) so no
        # intermediate CSVs exist at all — make that obvious in the UI.
        inter = os.path.join(out_dir, "intermediate")
        stage_csvs = glob.glob(os.path.join(inter, "stage", "*.csv")) if os.path.isdir(inter) else []
        if not stage_csvs:
            raise CaisrError(
                "CAISR preprocess produced no staging output. The EDF is missing "
                "channels CAISR requires (need chest+abd effort, EEG, EOG, SpO2, ECG). "
                "Re-upload after the latest sanitizer, or use a full PSG export."
            )
        raise CaisrError("CAISR completed but no combined annotation CSV was produced")

    with open(combined, encoding="utf-8", errors="replace") as fh:
        stage_epochs, events = parse_caisr_csv(fh.read())

    # Preview traces + SpO2 enrichment from the (sanitized) EDF when available.
    signals = None
    spo2_enriched = False
    if os.path.splitext(dest)[1].lower() == ".edf":
        try:
            report(0.9, "Extracting SpO2 / EEG / flow preview")
            preview = read_edf_channels(
                dest,
                want=["spo2", "sao2", "ptaf", "airflow", "c4", "c3", "chest", "abd"],
                target_fs=2.0,
            )
            signals = {
                "fs": preview["fs"],
                "channels": preview["channels"],
                "duration_sec": preview["duration_sec"],
                "synthetic": False,
            }
            spo2 = pick_spo2(preview["channels"])
            if spo2:
                events = enrich_events_with_spo2(events, spo2, float(preview["fs"]))
                spo2_enriched = True
        except Exception:
            signals = None

    m = job.get("meta", {})
    population = m.get("population") or "adult"
    hyp = build_hypnogram(stage_epochs, 30.0, None, source="caisr")
    metrics = compute_metrics(hyp, events)
    if signals and spo2_enriched:
        spo2 = pick_spo2(signals["channels"])
        if spo2:
            metrics = apply_spo2_to_metrics(metrics, spo2, float(signals["fs"]))

    summary = build_clinical_summary(
        metrics,
        population=population,
        age=m.get("age"),
        study_type=m.get("study_type") or "diagnostic",
        has_staging=bool(stage_epochs),
        has_events=bool(events),
    )
    uid = f"upload-{job['id']}"
    now = datetime.now(timezone.utc).isoformat()
    sanitize_steps = list(sanitize_info.get("steps") or [])
    if combine_fallback:
        sanitize_steps.append("combined_from_intermediate_csvs")
    if spo2_enriched:
        sanitize_steps.append("spo2_nadir_odi_from_waveform")

    meta = {
        "uid": uid,
        "patient_uid": uid,
        "cohort": m.get("cohort") or "UPLOAD",
        "population": population,
        "age": m.get("age"),
        "sex": m.get("sex"),
        "display_name": m.get("display_name") or job["filename"],
        "study_type": m.get("study_type") or "diagnostic",
        "study_type_raw": m.get("study_type") or "diagnostic",
        "creation_time": now,
        "annotation_source": "caisr",
        "has_staging": bool(stage_epochs),
        "has_events": bool(events),
        "n_events": len(events),
        "start_clock": None,
        "uploaded": True,
        "provenance": {
            "scorer": "caisr",
            "caisr_images": CAISR_IMAGES,
            "psg_core_version": PSG_CORE_VERSION,
            "pipeline": "docker/run_caisr.py",
            "source_filename": job.get("filename"),
            "sanitized": bool(sanitize_info.get("steps")),
            "sanitize_steps": sanitize_steps,
            "spo2_from_waveform": spo2_enriched,
            "combine_fallback": combine_fallback,
            "created_at": now,
        },
    }
    hypnogram = {
        "epoch_length_sec": 30.0,
        "start_clock": None,
        "stages": hyp.stages,
        "source": "caisr",
    }
    write_study(
        data_root,
        uid,
        meta=meta,
        hypnogram=hypnogram,
        events=events_to_json(events),
        metrics=metrics,
        summary=summary,
        signals=signals,
    )
    return uid


def _find_combined_csv(out_dir: str) -> Optional[str]:
    """Locate CAISR's combined per-sample annotation CSV.

    The report task writes it to ``caisr_output/.../caisr_annotations/caisr_{id}.csv``
    (also referenced as ``combined/``). We prefer files whose header actually
    carries the combined columns (``stage`` + ``resp``) so intermediate per-task
    CSVs are not picked up by mistake.
    """
    candidates: list[str] = []
    for pat in ("caisr_annotations", "combined"):
        candidates += glob.glob(os.path.join(out_dir, "**", pat, "*.csv"), recursive=True)
    candidates += glob.glob(os.path.join(out_dir, "**", "caisr_*.csv"), recursive=True)
    # De-dup while preserving order.
    seen: set[str] = set()
    ordered = [c for c in candidates if not (c in seen or seen.add(c))]

    def _is_combined(path: str) -> bool:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                header = fh.readline().lower()
        except OSError:
            return False
        return "stage" in header and "resp" in header

    for c in ordered:
        if _is_combined(c):
            return c
    return ordered[0] if ordered else None
