"""In-memory registry + on-disk artifact access."""

from __future__ import annotations

import json
import os
import threading
from typing import Optional

from .settings import settings

from psg_core.artifacts import read_artifact, study_exists


class Store:
    def __init__(self, data_root: str):
        self.data_root = data_root
        self._lock = threading.RLock()
        self._index: list[dict] = []
        self._sessions_by_uid: dict[str, dict] = {}
        self._cohorts: list[dict] = []
        self.reload()

    def reload(self) -> None:
        with self._lock:
            self._index = self._load_json("index.json", [])
            self._cohorts = self._load_json("cohorts.json", [])
            sessions = self._load_json("sessions.json", [])
            self._sessions_by_uid = {s["uid"]: s for s in sessions}

    def _load_json(self, name: str, default):
        path = os.path.join(settings.registry_dir, name)
        if not os.path.exists(path):
            return default
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return default

    # ---- registry ----
    def cohorts(self) -> list[dict]:
        return self._cohorts

    def session(self, uid: str) -> Optional[dict]:
        return self._sessions_by_uid.get(uid)

    def worklist(
        self,
        *,
        cohort: Optional[str] = None,
        population: Optional[str] = None,
        study_type: Optional[str] = None,
        cached_only: bool = False,
        search: Optional[str] = None,
        review_status: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict:
        with self._lock:
            rows = self._index
        out: list[dict] = []
        for r in rows:
            if cohort and r.get("cohort") != cohort:
                continue
            if population and r.get("population") != population:
                continue
            if study_type and r.get("study_type") != study_type:
                continue
            cached = study_exists(self.data_root, r["uid"])
            if cached_only and not cached:
                continue
            if search:
                s = search.lower()
                hay = f"{r.get('uid','')} {r.get('patient_uid','')} {r.get('cohort','')}".lower()
                if s not in hay:
                    continue
            item = dict(r)
            item["cached"] = cached
            out.append(item)

        # Cached (analyzed) studies float to the top of the worklist.
        out.sort(key=lambda x: (not x.get("cached"), x.get("cohort", ""), x.get("uid", "")))

        if review_status or severity:
            filtered = self._triage_filter(
                out,
                review_status=review_status,
                severity=severity,
                limit=limit,
                offset=offset,
            )
            return {
                "total": filtered["total"],
                "count": len(filtered["items"]),
                "offset": offset,
                "items": filtered["items"],
            }

        total = len(out)
        page = out[offset : offset + limit]
        enriched = []
        for item in page:
            if item.get("cached"):
                meta = read_artifact(self.data_root, item["uid"], "meta") or {}
                metrics = read_artifact(self.data_root, item["uid"], "metrics") or {}
                summary = read_artifact(self.data_root, item["uid"], "summary") or {}
                review = meta.get("review") or {}
                item = dict(item)
                item["display_name"] = meta.get("display_name")
                item["ahi"] = metrics.get("ahi")
                item["osa_severity"] = summary.get("osa_severity")
                item["overall_severity"] = summary.get("overall_severity")
                item["review_status"] = review.get("status") or "pending_review"
                item["annotation_source"] = meta.get("annotation_source")
            else:
                item = dict(item)
                item["review_status"] = None
            enriched.append(item)

        return {"total": total, "count": len(enriched), "offset": offset, "items": enriched}

    def _triage_filter(
        self,
        candidates: list[dict],
        *,
        review_status: Optional[str],
        severity: Optional[str],
        limit: int,
        offset: int,
    ) -> dict:
        matched: list[dict] = []
        for r in candidates:
            if not r.get("cached"):
                continue
            meta = read_artifact(self.data_root, r["uid"], "meta") or {}
            metrics = read_artifact(self.data_root, r["uid"], "metrics") or {}
            summary = read_artifact(self.data_root, r["uid"], "summary") or {}
            review = meta.get("review") or {}
            status = review.get("status") or "pending_review"
            osa = summary.get("osa_severity")
            if review_status and status != review_status:
                continue
            if severity and osa != severity:
                continue
            item = dict(r)
            item["display_name"] = meta.get("display_name")
            item["ahi"] = metrics.get("ahi")
            item["osa_severity"] = osa
            item["overall_severity"] = summary.get("overall_severity")
            item["review_status"] = status
            item["annotation_source"] = meta.get("annotation_source")
            matched.append(item)
        # Pending / severe float to top for clinic queue
        rank = {"pending_review": 0, "in_review": 1, "reviewed": 2, "signed_off": 3}
        sev_rank = {"severe": 0, "moderate": 1, "mild": 2, "normal": 3, "unknown": 4}
        matched.sort(
            key=lambda x: (
                rank.get(x.get("review_status") or "", 9),
                sev_rank.get(x.get("osa_severity") or "", 9),
                -(x.get("ahi") or 0),
            )
        )
        page = matched[offset : offset + limit]
        return {"total": len(matched), "items": page}

    def patient(self, patient_uid: str) -> Optional[dict]:
        with self._lock:
            sessions = [s for s in self._sessions_by_uid.values() if s.get("patient_uid") == patient_uid]
        if not sessions:
            return None
        sessions.sort(key=lambda s: s.get("creation_time") or "")
        first = sessions[0]
        return {
            "patient_uid": patient_uid,
            "cohort": first.get("cohort"),
            "population": first.get("population"),
            "n_sessions": len(sessions),
            "sessions": [
                {
                    "uid": s["uid"],
                    "session_id": s.get("session_id"),
                    "creation_time": s.get("creation_time"),
                    "age": s.get("age"),
                    "study_type": s.get("study_type"),
                    "cached": study_exists(self.data_root, s["uid"]),
                }
                for s in sessions
            ],
        }

    # ---- artifacts ----
    def is_cached(self, uid: str) -> bool:
        return study_exists(self.data_root, uid)

    def artifact(self, uid: str, name: str):
        return read_artifact(self.data_root, uid, name)


store = Store(settings.data_root)
