"""Combine CAISR per-task CSVs into the 2 Hz combined annotation table.

The official ``caisr_report`` step only emits ``caisr_annotations/caisr_{id}.csv``
when *all* of stage/arousal/resp/limb produced a matching file. Upstream
``caisr_limb`` silently skips recordings with no leg-EMG channels (common on
synthetic / truncated EDFs) and writes nothing — so report's intersection is
empty and the dashboard sees "no combined annotation CSV".

This module rebuilds the combined CSV from whatever intermediate task outputs
exist, synthesizing an all-zero limb (or other missing) stream from the stage
timeline so scoring can still complete.
"""

from __future__ import annotations

import csv
import os
from typing import Optional


TASKS = ("stage", "arousal", "resp", "limb")
# CAISR task CSVs are written at these rates (rows/sec of recording).
TASK_HZ = {"stage": 1, "arousal": 2, "resp": 1, "limb": 1}
TARGET_HZ = 2


def _read_csv(path: str) -> tuple[list[str], list[dict]]:
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    return fields, rows


def _write_csv(path: str, fields: list[str], rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _study_id_from_name(filename: str, task: str) -> str:
    # e.g. ebc44d1b0659_stage.csv -> ebc44d1b0659
    stem = os.path.splitext(os.path.basename(filename))[0]
    suffix = f"_{task}"
    if stem.endswith(suffix):
        return stem[: -len(suffix)]
    return stem


def _find_task_csv(intermediate: str, task: str, study_id: Optional[str] = None) -> Optional[str]:
    task_dir = os.path.join(intermediate, task)
    if not os.path.isdir(task_dir):
        return None
    for name in sorted(os.listdir(task_dir)):
        if not name.lower().endswith(".csv"):
            continue
        path = os.path.join(task_dir, name)
        if study_id is None or _study_id_from_name(name, task) == study_id:
            return path
    return None


def _discover_study_id(intermediate: str) -> Optional[str]:
    # Prefer stage (required for a meaningful report); fall back to any task.
    for task in TASKS:
        path = _find_task_csv(intermediate, task)
        if path:
            return _study_id_from_name(path, task)
    return None


def _synthesize_limb(stage_path: str, dest: str) -> None:
    """Write an all-zero limb CSV matching the stage timeline (1 Hz)."""
    _, stage_rows = _read_csv(stage_path)
    rows = []
    for r in stage_rows:
        rows.append(
            {
                "start_idx": r.get("start_idx", ""),
                "end_idx": r.get("end_idx", ""),
                "limb": "0",
                "plm": "0",
                "prob_no": "1.0",
                "prob_limb": "0.0",
            }
        )
    _write_csv(dest, ["start_idx", "end_idx", "limb", "plm", "prob_no", "prob_limb"], rows)


def _upsample_to_2hz(rows: list[dict], src_hz: int) -> list[dict]:
    if src_hz == TARGET_HZ:
        return rows
    if src_hz <= 0 or TARGET_HZ % src_hz != 0:
        raise ValueError(f"unsupported task rate {src_hz} Hz for upsample to {TARGET_HZ} Hz")
    factor = TARGET_HZ // src_hz
    out: list[dict] = []
    for r in rows:
        out.extend([dict(r) for _ in range(factor)])
    return out


def _rename_task_columns(task: str, fields: list[str], rows: list[dict]) -> tuple[list[str], list[dict]]:
    """Mirror caisr_report.combine_caisr_outputs column renaming."""
    keep_raw = {task, "start_idx", "end_idx"}
    mapping: dict[str, str] = {}
    for f in fields:
        if f in keep_raw:
            mapping[f] = f
        else:
            mapping[f] = f"{task}_{f}"
    # Drop limb probability columns the official combiner discards.
    drop = {"limb_prob_no", "limb_prob_limb"}
    new_fields = [mapping[f] for f in fields if mapping[f] not in drop]
    new_rows = []
    for r in rows:
        nr = {mapping[k]: v for k, v in r.items() if k in mapping and mapping[k] not in drop}
        new_rows.append(nr)
    return new_fields, new_rows


def combine_intermediate(out_dir: str) -> Optional[str]:
    """Build ``caisr_annotations/caisr_{id}.csv`` from intermediate task CSVs.

    Returns the path of the combined CSV, or None if nothing usable was found.
    """
    intermediate = os.path.join(out_dir, "intermediate")
    if not os.path.isdir(intermediate):
        return None

    study_id = _discover_study_id(intermediate)
    if not study_id:
        return None

    stage_path = _find_task_csv(intermediate, "stage", study_id)
    if not stage_path:
        return None

    # Ensure limb exists (upstream skips when EMG channels are absent/zero).
    limb_path = _find_task_csv(intermediate, "limb", study_id)
    if not limb_path:
        limb_dir = os.path.join(intermediate, "limb")
        os.makedirs(limb_dir, exist_ok=True)
        limb_path = os.path.join(limb_dir, f"{study_id}_limb.csv")
        _synthesize_limb(stage_path, limb_path)

    # Optional missing arousal/resp → synthesize zeros from stage.
    for task, cols in (
        ("arousal", ["arousal", "prob_no", "prob_arousal", "pp_trace"]),
        ("resp", ["resp"]),
    ):
        if _find_task_csv(intermediate, task, study_id):
            continue
        _, stage_rows = _read_csv(stage_path)
        # arousal is 2 Hz; stage is 1 Hz → duplicate.
        if task == "arousal":
            rows = []
            for r in stage_rows:
                try:
                    s = int(float(r["start_idx"]))
                    e = int(float(r["end_idx"]))
                except (KeyError, ValueError, TypeError):
                    continue
                mid = s + (e - s) // 2
                for a, b in ((s, mid), (mid, e)):
                    rows.append(
                        {
                            "start_idx": str(a),
                            "end_idx": str(b),
                            "arousal": "0",
                            "prob_no": "1.0",
                            "prob_arousal": "0.0",
                            "pp_trace": "0.0",
                        }
                    )
            fields = ["start_idx", "end_idx"] + cols
        else:
            rows = [
                {
                    "start_idx": r.get("start_idx", ""),
                    "end_idx": r.get("end_idx", ""),
                    "resp": "0",
                }
                for r in stage_rows
            ]
            fields = ["start_idx", "end_idx"] + cols
        dest = os.path.join(intermediate, task, f"{study_id}_{task}.csv")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        _write_csv(dest, fields, rows)

    # Load + upsample each task to 2 Hz, then column-bind.
    combined_fields: list[str] = []
    combined_cols: dict[str, list[str]] = {}
    n_rows: Optional[int] = None

    for task in TASKS:
        path = _find_task_csv(intermediate, task, study_id)
        if not path:
            return None
        fields, rows = _read_csv(path)
        rows = _upsample_to_2hz(rows, TASK_HZ[task])
        fields, rows = _rename_task_columns(task, fields, rows)

        # Only keep start_idx/end_idx from arousal (matches official combiner).
        if task != "arousal":
            fields = [f for f in fields if f not in ("start_idx", "end_idx")]
            for r in rows:
                r.pop("start_idx", None)
                r.pop("end_idx", None)

        if n_rows is None:
            n_rows = len(rows)
        else:
            n_rows = min(n_rows, len(rows))

        for f in fields:
            if f not in combined_fields:
                combined_fields.append(f)
            combined_cols[f] = [r.get(f, "") for r in rows]

    assert n_rows is not None
    # Truncate all columns to the shared length.
    out_rows = []
    for i in range(n_rows):
        out_rows.append({f: combined_cols[f][i] for f in combined_fields})

    # Coerce empties / NaNs in integer-ish columns to 9 (CAISR convention for unknown).
    intish = [f for f in combined_fields if "prob" not in f]
    for r in out_rows:
        for f in intish:
            v = (r.get(f) or "").strip()
            if v == "" or v.lower() in ("nan", "none"):
                r[f] = "9"

    # Put start/end first when present.
    ordered = [f for f in ("start_idx", "end_idx") if f in combined_fields]
    ordered += [f for f in combined_fields if f not in ordered]

    dest = os.path.join(out_dir, "caisr_annotations", f"caisr_{study_id}.csv")
    _write_csv(dest, ordered, out_rows)
    return dest
