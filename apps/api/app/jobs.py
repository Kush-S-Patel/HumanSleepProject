"""Upload + analysis job manager.

Two ingestion paths:

* HSP annotation CSV (``*_annotations.csv``): parsed directly by ``psg_core``
  into a full report - works with no extra dependencies.
* EDF / H5 raw signals: routed to the CAISR docker pipeline for automated
  scoring. If the CAISR images are not installed, the job is marked
  ``needs_setup`` with actionable instructions rather than failing silently.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Optional

from .settings import settings
from .store import store

from psg_core.artifacts import events_to_json, write_study
from psg_core.cds import build_clinical_summary
from psg_core.events import parse_annotations_csv
from psg_core.hypnogram import build_hypnogram
from psg_core.metrics import compute_metrics

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_NEEDS_SETUP = "needs_setup"


class JobManager:
    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._lock = threading.RLock()
        os.makedirs(settings.uploads_dir, exist_ok=True)
        os.makedirs(settings.jobs_dir, exist_ok=True)

    def _set(self, job_id: str, **fields) -> None:
        with self._lock:
            self._jobs[job_id].update(fields)
            self._jobs[job_id]["updated_at"] = time.time()
            self._persist(self._jobs[job_id])

    def _persist(self, job: dict) -> None:
        path = os.path.join(settings.jobs_dir, f"{job['id']}.json")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(job, fh)
        except OSError:
            pass

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                return dict(job)
        path = os.path.join(settings.jobs_dir, f"{job_id}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        return None

    def create(self, *, filename: str, saved_path: str, meta: dict) -> dict:
        job_id = uuid.uuid4().hex[:12]
        job = {
            "id": job_id,
            "filename": filename,
            "saved_path": saved_path,
            "status": STATUS_QUEUED,
            "progress": 0.0,
            "message": "Queued for analysis",
            "study_uid": None,
            "meta": meta,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        with self._lock:
            self._jobs[job_id] = job
            self._persist(job)
        threading.Thread(target=self._run, args=(job_id,), daemon=True).start()
        return dict(job)

    # ---- execution ----
    def _run(self, job_id: str) -> None:
        job = self.get(job_id)
        if not job:
            return
        path = job["saved_path"]
        ext = os.path.splitext(path)[1].lower()
        try:
            self._set(job_id, status=STATUS_RUNNING, progress=0.1, message="Analyzing")
            if ext == ".csv":
                uid = self._analyze_annotation_csv(job)
                self._set(
                    job_id,
                    status=STATUS_DONE,
                    progress=1.0,
                    message="Report ready",
                    study_uid=uid,
                )
            elif ext in (".edf", ".h5"):
                self._analyze_signals(job_id, job, path, ext)
            else:
                self._set(
                    job_id,
                    status=STATUS_FAILED,
                    message=f"Unsupported file type '{ext}'. Upload an HSP annotation .csv, or an .edf/.h5 recording.",
                )
        except Exception as exc:  # pragma: no cover - defensive
            self._set(job_id, status=STATUS_FAILED, message=f"Analysis failed: {exc}")
        finally:
            store.reload()

    def _analyze_annotation_csv(self, job: dict) -> str:
        with open(job["saved_path"], encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        parsed = parse_annotations_csv(text)
        if not parsed.stage_epochs and not parsed.events:
            raise ValueError("No sleep stages or events found - is this an HSP annotation CSV?")

        m = job.get("meta", {})
        population = m.get("population") or "adult"
        age = m.get("age")
        study_type = m.get("study_type") or "diagnostic"

        hyp = build_hypnogram(
            parsed.stage_epochs, parsed.epoch_length_sec, parsed.start_clock, source="human"
        )
        metrics = compute_metrics(hyp, parsed.events)
        summary = build_clinical_summary(
            metrics,
            population=population,
            age=age,
            study_type=study_type,
            has_staging=bool(parsed.stage_epochs),
            has_events=bool(parsed.events),
        )
        uid = f"upload-{job['id']}"
        from datetime import datetime, timezone

        from psg_core import __version__ as psg_ver

        now = datetime.now(timezone.utc).isoformat()
        meta = {
            "uid": uid,
            "patient_uid": uid,
            "cohort": m.get("cohort") or "UPLOAD",
            "population": population,
            "age": age,
            "sex": m.get("sex"),
            "display_name": m.get("display_name") or job["filename"],
            "study_type": study_type,
            "study_type_raw": study_type,
            "creation_time": now,
            "annotation_source": "human",
            "has_staging": bool(parsed.stage_epochs),
            "has_events": bool(parsed.events),
            "n_events": len(parsed.events),
            "start_clock": parsed.start_clock,
            "uploaded": True,
            "provenance": {
                "scorer": "human",
                "psg_core_version": psg_ver,
                "source_filename": job.get("filename"),
                "sanitize_steps": [],
                "created_at": now,
            },
        }
        hypnogram = {
            "epoch_length_sec": hyp.epoch_length_sec,
            "start_clock": hyp.start_clock,
            "stages": hyp.stages,
            "source": "human",
        }
        write_study(
            settings.data_root,
            uid,
            meta=meta,
            hypnogram=hypnogram,
            events=events_to_json(parsed.events),
            metrics=metrics,
            summary=summary,
        )
        return uid

    def _analyze_signals(self, job_id: str, job: dict, path: str, ext: str) -> None:
        from .caisr_runner import CaisrError, CaisrNotAvailable, run_caisr

        if not settings.enable_caisr:
            self._set(
                job_id,
                status=STATUS_NEEDS_SETUP,
                message="CAISR scoring is disabled (HSP_ENABLE_CAISR=0). Enable it to score raw EDF/H5.",
            )
            return
        try:
            self._set(job_id, progress=0.2, message="Running CAISR sleep AI pipeline (this can take several minutes)")
            uid = run_caisr(
                path,
                job=job,
                data_root=settings.data_root,
                progress_cb=lambda p, msg: self._set(job_id, progress=p, message=msg),
            )
            self._set(job_id, status=STATUS_DONE, progress=1.0, message="Report ready", study_uid=uid)
        except CaisrNotAvailable as exc:
            self._set(job_id, status=STATUS_NEEDS_SETUP, message=str(exc))
        except CaisrError as exc:
            self._set(job_id, status=STATUS_FAILED, message=str(exc))


jobs = JobManager()
