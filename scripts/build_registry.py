"""Build the patient-level registry JSON consumed by the API.

Usage:
    python scripts/build_registry.py

Reads every ``metadata/*.csv`` and writes:
    data/registry/sessions.json
    data/registry/patients.json
    data/registry/cohorts.json
    data/registry/index.json   (lightweight worklist rows)
"""

from __future__ import annotations

import argparse
import json
import os

from _common import data_root, ensure_dir, metadata_dir

from psg_core.registry import build_registry


def _write(path: str, payload) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metadata-dir", default=metadata_dir())
    ap.add_argument("--data-root", default=data_root())
    args = ap.parse_args()

    print(f"[registry] reading metadata from {args.metadata_dir}")
    reg = build_registry(args.metadata_dir)
    out = os.path.join(args.data_root, "registry")

    _write(os.path.join(out, "sessions.json"), reg["sessions"])
    _write(os.path.join(out, "patients.json"), reg["patients"])
    _write(os.path.join(out, "cohorts.json"), reg["cohorts"])

    # Lightweight worklist index (one row per session).
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
            "likert_scale": s["likert_scale"],
        }
        for s in reg["sessions"]
    ]
    _write(os.path.join(out, "index.json"), index)

    print(
        f"[registry] wrote {reg['n_sessions']} sessions / {reg['n_patients']} patients "
        f"across {len(reg['cohorts'])} cohorts -> {out}"
    )
    for c in sorted(reg["cohorts"], key=lambda x: x["cohort"]):
        print(f"  {c['cohort']:6s} {c['population']:9s} {c['n_sessions']:>7} sessions  {c['n_patients']:>7} patients")


if __name__ == "__main__":
    main()
