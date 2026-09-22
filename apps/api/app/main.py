"""FastAPI application: worklist, study reports, uploads, and CAISR jobs."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from psg_core.artifacts import write_artifact
from psg_core.cds import build_clinical_summary
from psg_core.events import ScoredEvent
from psg_core.export import (
    clinician_report_html,
    clinician_report_pdf,
    events_to_bids_tsv,
    study_export_json,
)
from psg_core.hypnogram import Hypnogram
from psg_core.metrics import compute_metrics

from .jobs import jobs
from .settings import settings
from .store import store

app = FastAPI(
    title="Sleep Clinic AI Dashboard API",
    version="0.1.0",
    description="CAISR-backed clinical decision support over Human Sleep Project PSG data.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "data_root": settings.data_root,
        "n_worklist": store.worklist(limit=1)["total"],
        "caisr_enabled": settings.enable_caisr,
    }


@app.post("/api/admin/reload")
def reload_registry() -> dict:
    store.reload()
    return {"status": "reloaded", "n_worklist": store.worklist(limit=1)["total"]}


@app.get("/api/cohorts")
def cohorts() -> dict:
    return {"cohorts": store.cohorts()}


def _enrich_concordance(report: dict) -> dict:
    """Add Bland–Altman points and per-cohort κ from per_session rows."""
    sessions = report.get("per_session") or []
    ahi = dict(report.get("ahi_agreement") or {})
    points = []
    for s in sessions:
        h, c = s.get("human_ahi"), s.get("caisr_ahi")
        if h is None or c is None:
            continue
        points.append(
            {
                "uid": s.get("uid"),
                "cohort": s.get("cohort"),
                "human": h,
                "caisr": c,
                "mean": round((h + c) / 2.0, 3),
                "diff": round(h - c, 3),
            }
        )
    ahi["points"] = points
    report = dict(report)
    report["ahi_agreement"] = ahi

    by_cohort: dict[str, dict] = {}
    for s in sessions:
        c = s.get("cohort") or "?"
        bucket = by_cohort.setdefault(c, {"n": 0, "kappas": [], "accuracies": []})
        bucket["n"] += 1
        if s.get("staging_kappa") is not None:
            bucket["kappas"].append(s["staging_kappa"])
        if s.get("staging_accuracy") is not None:
            bucket["accuracies"].append(s["staging_accuracy"])
    report["by_cohort"] = {
        c: {
            "n": v["n"],
            "mean_kappa": round(sum(v["kappas"]) / len(v["kappas"]), 4) if v["kappas"] else None,
            "mean_accuracy": round(sum(v["accuracies"]) / len(v["accuracies"]), 4)
            if v["accuracies"]
            else None,
        }
        for c, v in sorted(by_cohort.items())
    }
    return report


@app.get("/api/eval/concordance")
def concordance() -> dict:
    """CAISR-vs-human concordance report (scripts/evaluate_concordance.py)."""
    path = os.path.join(settings.data_root, "eval", "concordance.json")
    if not os.path.exists(path):
        raise HTTPException(
            status_code=404,
            detail="no concordance report yet; run scripts/evaluate_concordance.py",
        )
    with open(path, encoding="utf-8") as fh:
        report = json.load(fh)
    return _enrich_concordance(report)


@app.get("/api/worklist")
def worklist(
    cohort: str | None = None,
    population: str | None = None,
    study_type: str | None = None,
    cached_only: bool = False,
    search: str | None = None,
    review_status: str | None = None,
    severity: str | None = None,
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
) -> dict:
    return store.worklist(
        cohort=cohort,
        population=population,
        study_type=study_type,
        cached_only=cached_only,
        search=search,
        review_status=review_status,
        severity=severity,
        limit=limit,
        offset=offset,
    )


@app.get("/api/patients/{patient_uid}")
def patient(patient_uid: str) -> dict:
    p = store.patient(patient_uid)
    if not p:
        raise HTTPException(status_code=404, detail="patient not found")
    return p


def _require_cached(uid: str) -> None:
    if not store.is_cached(uid):
        session = store.session(uid)
        if session is None:
            raise HTTPException(status_code=404, detail="study not found in registry")
        raise HTTPException(
            status_code=409,
            detail="study not analyzed yet; build its artifacts with scripts/build_cache.py --uids " + uid,
        )


@app.get("/api/studies/{uid}")
def study(uid: str) -> dict:
    _require_cached(uid)
    meta = store.artifact(uid, "meta")
    metrics = store.artifact(uid, "metrics")
    summary = store.artifact(uid, "summary")
    return {"meta": meta, "metrics": metrics, "summary": summary}


@app.get("/api/studies/{uid}/hypnogram")
def hypnogram(uid: str) -> dict:
    _require_cached(uid)
    return store.artifact(uid, "hypnogram")


@app.get("/api/studies/{uid}/events")
def events(uid: str) -> dict:
    _require_cached(uid)
    return store.artifact(uid, "events") or {"events": []}


@app.get("/api/studies/{uid}/signals")
def signals(uid: str) -> dict:
    _require_cached(uid)
    sig = store.artifact(uid, "signals")
    if sig is None:
        raise HTTPException(status_code=404, detail="no signal preview available for this study")
    return sig


def _comparison_for(uid: str) -> Optional[dict]:
    """AI vs human side-by-side: stored artifact, else concordance row."""
    stored = store.artifact(uid, "comparison")
    if stored:
        return stored
    path = os.path.join(settings.data_root, "eval", "concordance.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            report = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    for s in report.get("per_session") or []:
        if s.get("uid") == uid:
            return {
                "source": "concordance",
                "uid": uid,
                "human": {
                    "ahi": s.get("human_ahi"),
                    "staging_accuracy": None,
                    "staging_kappa": None,
                },
                "ai": {
                    "ahi": s.get("caisr_ahi"),
                    "staging_accuracy": s.get("staging_accuracy"),
                    "staging_kappa": s.get("staging_kappa"),
                },
                "n_epochs": s.get("n_epochs"),
                "cohort": s.get("cohort"),
            }
    return None


@app.get("/api/studies/{uid}/comparison")
def comparison(uid: str) -> dict:
    _require_cached(uid)
    cmp = _comparison_for(uid)
    if cmp is None:
        raise HTTPException(status_code=404, detail="no AI vs human comparison for this study")
    return cmp


@app.get("/api/studies/{uid}/epoch/{epoch_index}")
def epoch_window(uid: str, epoch_index: int, pad_epochs: int = Query(2, ge=0, le=10)) -> dict:
    """Raw preview traces + events around a hypnogram epoch (for QC)."""
    _require_cached(uid)
    hyp = store.artifact(uid, "hypnogram") or {}
    stages = hyp.get("stages") or []
    if epoch_index < 0 or epoch_index >= len(stages):
        raise HTTPException(status_code=404, detail="epoch out of range")
    epoch_sec = float(hyp.get("epoch_length_sec") or 30.0)
    t0 = max(0.0, (epoch_index - pad_epochs) * epoch_sec)
    t1 = (epoch_index + 1 + pad_epochs) * epoch_sec
    evs = (store.artifact(uid, "events") or {}).get("events") or []
    in_win = [
        e
        for e in evs
        if e.get("onset_sec", 0) < t1 and e.get("onset_sec", 0) + e.get("duration_sec", 0) > t0
    ]
    sig = store.artifact(uid, "signals")
    traces: dict[str, list[float]] = {}
    fs = 2.0
    if sig and sig.get("channels"):
        fs = float(sig.get("fs") or 2.0)
        i0 = int(t0 * fs)
        i1 = int(t1 * fs)
        for name, series in sig["channels"].items():
            # Prefer channels useful for QC
            low = name.lower()
            if any(k in low for k in ("spo2", "sao2", "ptaf", "airflow", "c4", "c3", "chest", "abd", "flow")):
                traces[name] = series[i0:i1]
    return {
        "epoch_index": epoch_index,
        "stage": stages[epoch_index],
        "epoch_length_sec": epoch_sec,
        "window_start_sec": t0,
        "window_end_sec": t1,
        "fs": fs,
        "traces": traces,
        "events": in_win,
        "stages_nearby": stages[max(0, epoch_index - pad_epochs) : epoch_index + 1 + pad_epochs],
    }


def _events_from_dicts(rows: list[dict]) -> list[ScoredEvent]:
    out: list[ScoredEvent] = []
    for e in rows:
        out.append(
            ScoredEvent(
                onset_sec=float(e.get("onset_sec") or 0),
                duration_sec=float(e.get("duration_sec") or 0),
                category=str(e.get("category") or "other"),
                subtype=str(e.get("subtype") or ""),
                nadir_spo2=e.get("nadir_spo2"),
            )
        )
    return out


def _recompute_and_save(uid: str, hyp: dict, events_payload: dict, meta: dict) -> dict:
    stages = hyp.get("stages") or []
    epoch_sec = float(hyp.get("epoch_length_sec") or 30.0)
    hyp_obj = Hypnogram(
        epoch_length_sec=epoch_sec,
        stages=stages,
        start_clock=hyp.get("start_clock"),
        source=hyp.get("source") or "override",
    )
    events = _events_from_dicts((events_payload or {}).get("events") or [])
    metrics = compute_metrics(hyp_obj, events)
    summary = build_clinical_summary(
        metrics,
        population=meta.get("population") or "adult",
        age=meta.get("age"),
        study_type=meta.get("study_type") or "diagnostic",
        has_staging=bool(stages),
        has_events=bool(events),
    )
    write_artifact(settings.data_root, uid, "hypnogram", hyp)
    write_artifact(settings.data_root, uid, "events", events_payload)
    write_artifact(settings.data_root, uid, "metrics", metrics)
    write_artifact(settings.data_root, uid, "summary", summary)
    write_artifact(settings.data_root, uid, "meta", meta)
    return {"meta": meta, "metrics": metrics, "summary": summary, "hypnogram": hyp, "events": events_payload}


class StageOverride(BaseModel):
    epoch_index: int
    stage: str


class EventOverride(BaseModel):
    action: str = Field(description="set | add | delete")
    index: Optional[int] = None
    event: Optional[dict[str, Any]] = None
    events: Optional[list[dict[str, Any]]] = None


class ReviewUpdate(BaseModel):
    status: str = Field(description="pending_review | in_review | reviewed | signed_off")
    reviewer: Optional[str] = None
    notes: Optional[str] = None


@app.get("/api/studies/{uid}/review")
def get_review(uid: str) -> dict:
    _require_cached(uid)
    meta = store.artifact(uid, "meta") or {}
    review = meta.get("review") or {
        "status": "pending_review",
        "reviewer": None,
        "notes": None,
        "updated_at": None,
        "history": [],
    }
    return review


@app.patch("/api/studies/{uid}/review")
def update_review(uid: str, body: ReviewUpdate) -> dict:
    """Clinic review lifecycle: pending → in_review → reviewed → signed_off."""
    _require_cached(uid)
    allowed = {"pending_review", "in_review", "reviewed", "signed_off"}
    if body.status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(allowed)}")
    meta = dict(store.artifact(uid, "meta") or {})
    prev = dict(meta.get("review") or {})
    history = list(prev.get("history") or [])
    now = datetime.now(timezone.utc).isoformat()
    history.append(
        {
            "status": body.status,
            "reviewer": body.reviewer or prev.get("reviewer"),
            "notes": body.notes if body.notes is not None else prev.get("notes"),
            "at": now,
        }
    )
    review = {
        "status": body.status,
        "reviewer": body.reviewer if body.reviewer is not None else prev.get("reviewer"),
        "notes": body.notes if body.notes is not None else prev.get("notes"),
        "updated_at": now,
        "history": history[-40:],
    }
    meta["review"] = review
    write_artifact(settings.data_root, uid, "meta", meta)
    return review


@app.patch("/api/studies/{uid}/hypnogram")
def override_stage(uid: str, body: StageOverride) -> dict:
    _require_cached(uid)
    meta = dict(store.artifact(uid, "meta") or {})
    if (meta.get("review") or {}).get("status") == "signed_off":
        raise HTTPException(status_code=409, detail="study is signed off; reopen review to edit")
    hyp = dict(store.artifact(uid, "hypnogram") or {})
    stages = list(hyp.get("stages") or [])
    if body.epoch_index < 0 or body.epoch_index >= len(stages):
        raise HTTPException(status_code=400, detail="epoch_index out of range")
    stage = body.stage.upper() if body.stage.upper() in ("W", "N1", "N2", "N3", "REM", "?") else body.stage
    if stage not in ("W", "N1", "N2", "N3", "REM", "?"):
        raise HTTPException(status_code=400, detail="stage must be W/N1/N2/N3/REM/?")
    stages[body.epoch_index] = stage
    hyp["stages"] = stages
    hyp["source"] = (hyp.get("source") or "caisr") + "+override"
    overrides = store.artifact(uid, "overrides") or {"stage": [], "events": []}
    overrides.setdefault("stage", []).append(
        {
            "epoch_index": body.epoch_index,
            "stage": stage,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )
    write_artifact(settings.data_root, uid, "overrides", overrides)
    events_payload = store.artifact(uid, "events") or {"events": []}
    return _recompute_and_save(uid, hyp, events_payload, meta)


@app.patch("/api/studies/{uid}/events")
def override_events(uid: str, body: EventOverride) -> dict:
    _require_cached(uid)
    meta = dict(store.artifact(uid, "meta") or {})
    if (meta.get("review") or {}).get("status") == "signed_off":
        raise HTTPException(status_code=409, detail="study is signed off; reopen review to edit")
    payload = dict(store.artifact(uid, "events") or {"events": []})
    rows = list(payload.get("events") or [])
    if body.action == "set" and body.events is not None:
        rows = list(body.events)
    elif body.action == "delete":
        if body.index is None or body.index < 0 or body.index >= len(rows):
            raise HTTPException(status_code=400, detail="index required for delete")
        rows.pop(body.index)
    elif body.action == "add":
        if not body.event:
            raise HTTPException(status_code=400, detail="event required for add")
        rows.append(body.event)
    else:
        raise HTTPException(status_code=400, detail="action must be set, add, or delete")
    payload["events"] = rows
    hyp = store.artifact(uid, "hypnogram") or {}
    overrides = store.artifact(uid, "overrides") or {"stage": [], "events": []}
    overrides.setdefault("events", []).append(
        {"action": body.action, "at": datetime.now(timezone.utc).isoformat()}
    )
    write_artifact(settings.data_root, uid, "overrides", overrides)
    return _recompute_and_save(uid, hyp, payload, meta)


@app.get("/api/studies/{uid}/export.json")
def export_json(uid: str) -> dict:
    _require_cached(uid)
    return study_export_json(
        meta=store.artifact(uid, "meta") or {},
        metrics=store.artifact(uid, "metrics") or {},
        summary=store.artifact(uid, "summary") or {},
        hypnogram=store.artifact(uid, "hypnogram"),
        events=store.artifact(uid, "events"),
        comparison=_comparison_for(uid),
    )


@app.get("/api/studies/{uid}/export.bids.tsv")
def export_bids(uid: str) -> Response:
    _require_cached(uid)
    evs = (store.artifact(uid, "events") or {}).get("events") or []
    hyp = store.artifact(uid, "hypnogram")
    tsv = events_to_bids_tsv(evs, hyp)
    return Response(
        content=tsv,
        media_type="text/tab-separated-values",
        headers={"Content-Disposition": f'attachment; filename="{uid}_events.tsv"'},
    )


@app.get("/api/studies/{uid}/export.html")
def export_html(uid: str) -> HTMLResponse:
    _require_cached(uid)
    html = clinician_report_html(
        meta=store.artifact(uid, "meta") or {},
        metrics=store.artifact(uid, "metrics") or {},
        summary=store.artifact(uid, "summary") or {},
        comparison=_comparison_for(uid),
    )
    return HTMLResponse(
        content=html,
        headers={"Content-Disposition": f'inline; filename="{uid}_report.html"'},
    )


@app.get("/api/studies/{uid}/export.pdf")
def export_pdf(uid: str) -> Response:
    _require_cached(uid)
    pdf = clinician_report_pdf(
        meta=store.artifact(uid, "meta") or {},
        metrics=store.artifact(uid, "metrics") or {},
        summary=store.artifact(uid, "summary") or {},
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{uid}_report.pdf"'},
    )


@app.post("/api/uploads")
async def upload(
    file: UploadFile = File(...),
    population: str = Form("adult"),
    age: float | None = Form(None),
    sex: str | None = Form(None),
    study_type: str = Form("diagnostic"),
    display_name: str | None = Form(None),
) -> dict:
    filename = os.path.basename(file.filename or "upload")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".csv", ".edf", ".h5"):
        raise HTTPException(status_code=400, detail="upload a .csv (HSP annotations), .edf, or .h5 file")

    os.makedirs(settings.uploads_dir, exist_ok=True)
    token = uuid.uuid4().hex[:12]
    saved_path = os.path.join(settings.uploads_dir, f"{token}{ext}")
    with open(saved_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)

    job = jobs.create(
        filename=filename,
        saved_path=saved_path,
        meta={
            "population": population,
            "age": age,
            "sex": sex,
            "study_type": study_type,
            "display_name": display_name or filename,
        },
    )
    return job


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    # Don't leak absolute server paths to the client.
    job = dict(job)
    job.pop("saved_path", None)
    return job
