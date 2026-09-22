"""Read/write compact per-study artifacts consumed by the API and dashboard.

Artifacts are stored as small JSON files under ``data/studies/<session_uid>/``.
JSON (rather than parquet) is used deliberately: a full night is ~1000 stage
epochs and a few hundred events, so files stay tiny and require no binary deps,
keeping the API dependency-light and the payloads directly serveable.

Layout::

    data/studies/<uid>/meta.json
    data/studies/<uid>/hypnogram.json
    data/studies/<uid>/events.json
    data/studies/<uid>/metrics.json
    data/studies/<uid>/summary.json
    data/studies/<uid>/signals.json      (optional preview traces)
    data/studies/<uid>/comparison.json   (optional AI vs human)
    data/studies/<uid>/overrides.json    (optional QC edits)
"""

from __future__ import annotations

import json
import os
from typing import Optional

from .events import ScoredEvent

ARTIFACT_FILES = {
    "meta": "meta.json",
    "hypnogram": "hypnogram.json",
    "events": "events.json",
    "metrics": "metrics.json",
    "summary": "summary.json",
    "signals": "signals.json",
    "comparison": "comparison.json",
    "overrides": "overrides.json",
}


def study_dir(root: str, uid: str) -> str:
    return os.path.join(root, "studies", uid)


def _write_json(path: str, payload) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def _read_json(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def events_to_json(events: list[ScoredEvent]) -> list[dict]:
    return [
        {
            "onset_sec": round(e.onset_sec, 3),
            "duration_sec": round(e.duration_sec, 3),
            "category": e.category,
            "subtype": e.subtype,
            "nadir_spo2": e.nadir_spo2,
        }
        for e in events
    ]


def write_study(
    root: str,
    uid: str,
    *,
    meta: dict,
    hypnogram: dict,
    events: list[dict],
    metrics: dict,
    summary: dict,
    signals: Optional[dict] = None,
    comparison: Optional[dict] = None,
) -> str:
    d = study_dir(root, uid)
    _write_json(os.path.join(d, ARTIFACT_FILES["meta"]), meta)
    _write_json(os.path.join(d, ARTIFACT_FILES["hypnogram"]), hypnogram)
    _write_json(os.path.join(d, ARTIFACT_FILES["events"]), {"events": events})
    _write_json(os.path.join(d, ARTIFACT_FILES["metrics"]), metrics)
    _write_json(os.path.join(d, ARTIFACT_FILES["summary"]), summary)
    if signals is not None:
        _write_json(os.path.join(d, ARTIFACT_FILES["signals"]), signals)
    if comparison is not None:
        _write_json(os.path.join(d, ARTIFACT_FILES["comparison"]), comparison)
    return d


def write_artifact(root: str, uid: str, name: str, payload) -> None:
    if name not in ARTIFACT_FILES:
        raise KeyError(f"unknown artifact {name}")
    _write_json(os.path.join(study_dir(root, uid), ARTIFACT_FILES[name]), payload)


def read_artifact(root: str, uid: str, name: str):
    if name not in ARTIFACT_FILES:
        return None
    path = os.path.join(study_dir(root, uid), ARTIFACT_FILES[name])
    if not os.path.exists(path):
        return None
    return _read_json(path)


def study_exists(root: str, uid: str) -> bool:
    return os.path.exists(os.path.join(study_dir(root, uid), ARTIFACT_FILES["meta"]))


def list_studies(root: str) -> list[str]:
    base = os.path.join(root, "studies")
    if not os.path.isdir(base):
        return []
    out = []
    for name in os.listdir(base):
        if study_exists(root, name):
            out.append(name)
    return sorted(out)
