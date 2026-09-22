"""Curate a demo set and build compact per-study artifacts from S3.

Downloads only the small (~40 KB) human annotation CSV per selected session,
parses it into a hypnogram + events, computes AASM metrics + a clinical
decision-support summary, and writes JSON artifacts under
``data/studies/<uid>/``.

Because it never touches EDF/H5 payloads, a curated demo set of a few hundred
studies costs only a few megabytes of disk.

Usage:
    python scripts/build_cache.py --per-cohort 12
    python scripts/build_cache.py --uids S0001-114602608-1 --force
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import tempfile
from typing import Optional

from _common import data_root, ensure_dir

import re

from psg_core.annotations import parse_study
from psg_core.artifacts import events_to_json, study_exists, write_study
from psg_core.cds import build_clinical_summary
from psg_core.hypnogram import build_hypnogram
from psg_core.metrics import compute_metrics
from psg_core.paths import S3_ALIAS, bids_eeg_prefix, s3_uri


def _age_band(age):
    if age is None:
        return "unknown"
    if age < 2:
        return "infant"
    if age < 13:
        return "child"
    if age < 18:
        return "adolescent"
    if age < 40:
        return "young_adult"
    if age < 65:
        return "adult"
    return "older_adult"


def load_sessions(root: str) -> list[dict]:
    path = os.path.join(root, "registry", "sessions.json")
    if not os.path.exists(path):
        raise SystemExit("registry not found; run scripts/build_registry.py first")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def curate(sessions: list[dict], per_cohort: int, seed: int) -> list[dict]:
    """Stratified pick: one session per patient, prefer diagnostic + staged."""
    rng = random.Random(seed)

    # Candidate filter: must have sleep annotations we can parse.
    candidates = [s for s in sessions if s.get("has_sleep_annotations")]

    # One session per patient (prefer diagnostic + staged + newest).
    def score(s):
        return (
            1 if s.get("study_type") == "diagnostic" else 0,
            1 if s.get("has_staging") else 0,
            1 if s.get("has_events_annotations") else 0,
            s.get("creation_time") or "",
        )

    by_patient: dict[str, dict] = {}
    for s in candidates:
        cur = by_patient.get(s["patient_uid"])
        if cur is None or score(s) > score(cur):
            by_patient[s["patient_uid"]] = s
    unique = list(by_patient.values())

    selected: list[dict] = []
    by_cohort: dict[str, list[dict]] = {}
    for s in unique:
        by_cohort.setdefault(s["cohort"], []).append(s)

    for cohort, items in sorted(by_cohort.items()):
        # Stratify across (study_type, age_band, sex) buckets for diversity.
        buckets: dict[tuple, list[dict]] = {}
        for s in items:
            key = (s.get("study_type"), _age_band(s.get("age")), s.get("sex"))
            buckets.setdefault(key, []).append(s)
        bucket_keys = list(buckets.keys())
        rng.shuffle(bucket_keys)
        picked: list[dict] = []
        i = 0
        # Round-robin across buckets until we hit the per-cohort target.
        while len(picked) < per_cohort and bucket_keys:
            key = bucket_keys[i % len(bucket_keys)]
            pool = buckets[key]
            if pool:
                picked.append(pool.pop(rng.randrange(len(pool))))
            else:
                bucket_keys.remove(key)
                if not bucket_keys:
                    break
                continue
            i += 1
        selected.extend(picked[:per_cohort])

    return selected


_SLEEP_RE = re.compile(r"sleep[_]?annotations\.csv$", re.IGNORECASE)
_EVENTS_RE = re.compile(r"events?[_]?annotations\.csv$", re.IGNORECASE)
_COMBINED_RE = re.compile(r"task-psg_annotations\.csv$", re.IGNORECASE)


def _s3_ls(prefix: str) -> list[str]:
    uri = s3_uri(prefix + "/", S3_ALIAS)
    try:
        res = subprocess.run(
            ["aws", "s3", "ls", uri],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        return []
    names = []
    for line in res.stdout.splitlines():
        parts = line.split()
        if parts and not line.strip().endswith("/") and parts[-1].endswith(".csv"):
            names.append(parts[-1])
    return names


def _cp(prefix: str, name: str, dest: str) -> bool:
    uri = s3_uri(f"{prefix}/{name}", S3_ALIAS)
    try:
        subprocess.run(
            ["aws", "s3", "cp", uri, dest, "--no-progress"],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def download_annotations(session: dict, tmp_dir: str) -> Optional[dict]:
    """List the session's eeg folder and fetch whatever annotation files exist.

    Returns a dict with any of ``combined`` / ``sleep`` / ``events`` text, or
    None if no human annotation files were found.
    """
    prefix = bids_eeg_prefix(session["cohort"], session["bids_folder"], session["session_id"])
    names = _s3_ls(prefix)
    if not names:
        return None

    combined = sleep = events = None
    for n in names:
        if _EVENTS_RE.search(n):
            events = n
        elif _SLEEP_RE.search(n):
            sleep = n
        elif _COMBINED_RE.search(n):
            combined = n

    out: dict = {}
    for kind, name in (("combined", combined), ("sleep", sleep), ("events", events)):
        if not name:
            continue
        dest = os.path.join(tmp_dir, f"{session['uid']}_{kind}.csv")
        if _cp(prefix, name, dest):
            with open(dest, encoding="utf-8", errors="replace") as fh:
                out[kind] = fh.read()
    return out or None


def build_study_artifacts(root: str, session: dict, ann: dict) -> None:
    parsed = parse_study(
        combined=ann.get("combined"),
        sleep=ann.get("sleep"),
        events=ann.get("events"),
    )
    hyp = build_hypnogram(
        parsed.stage_epochs,
        epoch_length_sec=parsed.epoch_length_sec,
        start_clock=parsed.start_clock,
        source="human",
    )
    metrics = compute_metrics(hyp, parsed.events)
    summary = build_clinical_summary(
        metrics,
        population=session.get("population", "adult"),
        age=session.get("age"),
        study_type=session.get("study_type_raw") or session.get("study_type"),
        has_staging=bool(parsed.stage_epochs),
        has_events=bool(parsed.events),
    )

    meta = {
        "uid": session["uid"],
        "patient_uid": session["patient_uid"],
        "cohort": session["cohort"],
        "population": session["population"],
        "age": session.get("age"),
        "sex": session.get("sex"),
        "study_type": session.get("study_type"),
        "study_type_raw": session.get("study_type_raw"),
        "creation_time": session.get("creation_time"),
        "annotation_source": "human",
        "has_staging": bool(parsed.stage_epochs),
        "has_events": bool(parsed.events),
        "n_events": len(parsed.events),
        "start_clock": parsed.start_clock,
    }
    hypnogram = {
        "epoch_length_sec": hyp.epoch_length_sec,
        "start_clock": hyp.start_clock,
        "stages": hyp.stages,
        "source": "human",
    }
    write_study(
        root,
        session["uid"],
        meta=meta,
        hypnogram=hypnogram,
        events=events_to_json(parsed.events),
        metrics=metrics,
        summary=summary,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default=data_root())
    ap.add_argument("--per-cohort", type=int, default=12, help="curated sessions per cohort")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--uids", nargs="*", help="explicit session uids to (re)build")
    ap.add_argument("--force", action="store_true", help="rebuild even if artifacts exist")
    args = ap.parse_args()

    sessions = load_sessions(args.data_root)
    by_uid = {s["uid"]: s for s in sessions}

    if args.uids:
        selected = [by_uid[u] for u in args.uids if u in by_uid]
        missing = [u for u in args.uids if u not in by_uid]
        for u in missing:
            print(f"  ! uid not in registry: {u}")
    else:
        selected = curate(sessions, args.per_cohort, args.seed)

    print(f"[cache] building {len(selected)} studies -> {args.data_root}")
    ensure_dir(os.path.join(args.data_root, "studies"))

    built, skipped, failed = 0, 0, 0
    manifest: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        for s in selected:
            if study_exists(args.data_root, s["uid"]) and not args.force:
                skipped += 1
                manifest.append({"uid": s["uid"], "status": "exists"})
                continue
            ann = download_annotations(s, tmp)
            if not ann:
                failed += 1
                print(f"  ! no annotation files found for {s['uid']} ({s['cohort']})")
                continue
            try:
                build_study_artifacts(args.data_root, s, ann)
                built += 1
                manifest.append({"uid": s["uid"], "status": "built", "cohort": s["cohort"]})
                print(f"  + {s['uid']}  ({s['cohort']}, {s.get('study_type')}, age {s.get('age')})")
            except Exception as exc:  # pragma: no cover - defensive
                failed += 1
                print(f"  ! parse/build failed for {s['uid']}: {exc}")

    man_path = os.path.join(args.data_root, "registry", "cache_manifest.json")
    ensure_dir(os.path.dirname(man_path))
    with open(man_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh)

    print(f"[cache] done. built={built} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
