"""Generate synthetic-but-realistic demo studies so the dashboard runs offline.

Produces the same compact artifacts as ``build_cache.py`` (hypnogram, events,
metrics, CDS summary, and a downsampled SpO2/airflow signal preview) plus a
self-contained registry, without touching S3. Real cached studies from
``build_cache.py`` coexist with these.

Usage:
    python scripts/make_sample_data.py --n 24
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random

from _common import data_root, ensure_dir

from psg_core.artifacts import events_to_json, write_study
from psg_core.cds import build_clinical_summary
from psg_core.events import (
    CAT_APNEA_CENTRAL,
    CAT_APNEA_OBSTRUCTIVE,
    CAT_AROUSAL,
    CAT_HYPOPNEA,
    CAT_LIMB,
    CAT_RERA,
    ScoredEvent,
)
from psg_core.hypnogram import build_hypnogram
from psg_core.metrics import compute_metrics
from psg_core.registry import COHORT_POPULATION

EPOCH = 30.0


def _generate_hypnogram(rng: random.Random, n_epochs: int, severity: float) -> list[str]:
    """Build a plausible night: sleep onset, NREM/REM cycles, awakenings."""
    stages: list[str] = []
    # Sleep latency: a few epochs of wake.
    lat = rng.randint(2, 20)
    stages += ["W"] * lat

    cycle_len = 0
    remaining = n_epochs - lat
    while remaining > 0:
        # One ~90 min cycle: N1 -> N2 -> N3 -> N2 -> REM
        n1 = rng.randint(1, 4)
        n2a = rng.randint(15, 30)
        n3 = max(0, rng.randint(6, 24) - int(severity * 10))  # SWS shrinks with severity
        n2b = rng.randint(10, 25)
        rem = rng.randint(8, 24) if cycle_len > 0 else rng.randint(2, 8)
        block = ["N1"] * n1 + ["N2"] * n2a + ["N3"] * n3 + ["N2"] * n2b + ["REM"] * rem
        # Fragment with arousals/awakenings proportional to severity.
        for i in range(len(block)):
            if rng.random() < 0.02 + severity * 0.06:
                block[i] = "W" if rng.random() < 0.4 else "N1"
        stages += block
        remaining -= len(block)
        cycle_len += 1
    stages = stages[:n_epochs]
    # Trailing wake.
    for i in range(len(stages) - rng.randint(1, 10), len(stages)):
        if 0 <= i < len(stages):
            stages[i] = "W"
    return stages


def _generate_events(rng: random.Random, stages: list[str], severity: float) -> list[ScoredEvent]:
    events: list[ScoredEvent] = []
    central_fraction = rng.random() * 0.5  # some patients central-predominant
    for i, stage in enumerate(stages):
        onset = i * EPOCH
        if stage in ("N1", "N2", "N3", "REM"):
            # REM and supine tend to worsen OSA.
            rem_boost = 1.6 if stage == "REM" else 1.0
            p_resp = min(0.9, severity * 0.18 * rem_boost)
            if rng.random() < p_resp:
                r = rng.random()
                dur = rng.uniform(10, 30)
                if r < 0.15:
                    cat, sub = CAT_RERA, "RERA"
                elif r < 0.15 + 0.5:
                    cat, sub = CAT_HYPOPNEA, "Hypopnea"
                elif rng.random() < central_fraction:
                    cat, sub = CAT_APNEA_CENTRAL, "Central apnea"
                else:
                    cat, sub = CAT_APNEA_OBSTRUCTIVE, "Obstructive apnea"
                nadir = None
                if cat in (CAT_HYPOPNEA, CAT_APNEA_OBSTRUCTIVE, CAT_APNEA_CENTRAL):
                    nadir = round(max(70.0, 94.0 - severity * rng.uniform(3, 14)), 1)
                events.append(
                    ScoredEvent(onset + rng.uniform(0, 20), dur, cat, sub, nadir_spo2=nadir)
                )
                # Respiratory arousal often follows.
                if rng.random() < 0.6:
                    events.append(
                        ScoredEvent(onset + dur, rng.uniform(2, 5), CAT_AROUSAL, "Respiratory arousal")
                    )
            # Spontaneous arousals.
            if rng.random() < 0.03 + severity * 0.02:
                events.append(ScoredEvent(onset, rng.uniform(3, 8), CAT_AROUSAL, "Spontaneous arousal"))
            # Limb movements.
            if rng.random() < 0.02:
                events.append(ScoredEvent(onset, rng.uniform(0.5, 5), CAT_LIMB, "Periodic limb movement"))
    return events


def _spo2_preview(stages: list[str], events: list[ScoredEvent], fs: float = 1.0) -> dict:
    """Downsampled SpO2 + airflow envelope reconstructed from events (synthetic)."""
    total_sec = int(len(stages) * EPOCH)
    n = int(total_sec * fs)
    spo2 = [97.0] * n
    airflow = [0.0] * n
    for i in range(n):
        t = i / fs
        airflow[i] = 0.6 + 0.4 * math.sin(t / 3.0)
    for e in events:
        if e.nadir_spo2 is None:
            continue
        c = int((e.onset_sec + e.duration_sec) * fs)
        depth = 97.0 - e.nadir_spo2
        for k in range(-int(10 * fs), int(20 * fs)):
            j = c + k
            if 0 <= j < n:
                # V-shaped desaturation then recovery.
                frac = 1.0 - min(1.0, abs(k) / (15 * fs))
                spo2[j] = min(spo2[j], 97.0 - depth * frac)
                airflow[j] *= 0.2 if k < 0 else 1.0
    return {
        "fs": fs,
        "channels": {
            "SpO2": [round(v, 1) for v in spo2],
            "Airflow": [round(v, 3) for v in airflow],
        },
        "synthetic": True,
    }


FIRST_NAMES = ["Alex", "Jordan", "Sam", "Taylor", "Casey", "Morgan", "Riley", "Jamie", "Avery", "Quinn"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default=data_root())
    ap.add_argument("--n", type=int, default=24, help="number of synthetic studies")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    ensure_dir(os.path.join(args.data_root, "studies"))

    cohorts = list(COHORT_POPULATION.items())
    synthetic_sessions: list[dict] = []

    for idx in range(args.n):
        cohort, population = cohorts[idx % len(cohorts)]
        is_ped = population == "pediatric"
        age = round(rng.uniform(1, 16), 0) if is_ped else round(rng.uniform(21, 88), 0)
        sex = rng.choice(["Male", "Female"])
        severity = rng.random() ** 1.3  # skew toward milder
        study_type = rng.choices(
            ["diagnostic", "split_night", "titration"], weights=[0.7, 0.15, 0.15]
        )[0]

        n_epochs = rng.randint(720, 1000)  # ~6-8.3 h
        stages = _generate_hypnogram(rng, n_epochs, severity)
        events = _generate_events(rng, stages, severity)

        hyp = build_hypnogram(stages, EPOCH, start_clock="22:30:00", source="synthetic")
        metrics = compute_metrics(hyp, events)
        summary = build_clinical_summary(
            metrics,
            population=population,
            age=age,
            study_type=study_type,
            has_staging=True,
            has_events=True,
        )

        pid = f"9{rng.randint(1000000, 9999999)}"
        uid = f"{cohort}-{pid}-1"
        meta = {
            "uid": uid,
            "patient_uid": f"{cohort}-{pid}",
            "cohort": cohort,
            "population": population,
            "age": age,
            "sex": sex,
            "display_name": f"{rng.choice(FIRST_NAMES)} {chr(65 + idx % 26)}.",
            "study_type": study_type,
            "study_type_raw": study_type,
            "creation_time": f"20{rng.randint(15, 25):02d}-0{rng.randint(1,9)}-1{rng.randint(0,9)} 22:30:00",
            "annotation_source": "synthetic",
            "has_staging": True,
            "has_events": True,
            "n_events": len(events),
            "start_clock": "22:30:00",
            "synthetic": True,
        }
        hypnogram = {
            "epoch_length_sec": EPOCH,
            "start_clock": "22:30:00",
            "stages": stages,
            "source": "synthetic",
        }
        write_study(
            args.data_root,
            uid,
            meta=meta,
            hypnogram=hypnogram,
            events=events_to_json(events),
            metrics=metrics,
            summary=summary,
            signals=_spo2_preview(stages, events),
        )
        synthetic_sessions.append(
            {
                "uid": uid,
                "patient_uid": meta["patient_uid"],
                "cohort": cohort,
                "population": population,
                "age": age,
                "sex": sex,
                "study_type": study_type,
                "study_type_raw": study_type,
                "bids_folder": f"sub-{cohort}{pid}",
                "session_id": "1",
                "patient_id": pid,
                "creation_time": meta["creation_time"],
                "has_staging": True,
                "has_sleep_annotations": True,
                "has_events_annotations": True,
                "likert_scale": rng.choice(["Outstanding", "Excellent", "Good"]),
                "quality_score": round(rng.uniform(0.7, 0.99), 2),
                "caisr_training_set": False,
                "synthetic": True,
            }
        )
        print(f"  + {uid}  ({cohort}, {study_type}, age {age}, AHI {metrics.get('ahi')})")

    # Merge synthetic sessions into the registry so they appear in the worklist.
    _merge_registry(args.data_root, synthetic_sessions)
    print(f"[sample] generated {len(synthetic_sessions)} synthetic studies -> {args.data_root}/studies")


def _merge_registry(root: str, synthetic: list[dict]) -> None:
    reg_dir = ensure_dir(os.path.join(root, "registry"))
    sessions_path = os.path.join(reg_dir, "sessions.json")
    index_path = os.path.join(reg_dir, "index.json")

    sessions = []
    if os.path.exists(sessions_path):
        with open(sessions_path, encoding="utf-8") as fh:
            sessions = json.load(fh)
    # Drop any prior synthetic rows, then append the new ones (idempotent).
    sessions = [s for s in sessions if not s.get("synthetic")] + synthetic
    with open(sessions_path, "w", encoding="utf-8") as fh:
        json.dump(sessions, fh, ensure_ascii=False)

    index = [
        {
            "uid": s["uid"],
            "patient_uid": s["patient_uid"],
            "cohort": s["cohort"],
            "population": s["population"],
            "age": s["age"],
            "sex": s["sex"],
            "study_type": s["study_type"],
            "creation_time": s["creation_time"],
            "has_staging": s["has_staging"],
            "has_events_annotations": s["has_events_annotations"],
            "likert_scale": s.get("likert_scale"),
            "synthetic": s.get("synthetic", False),
        }
        for s in sessions
    ]
    with open(index_path, "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False)


if __name__ == "__main__":
    main()
