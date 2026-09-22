"""Parse CAISR combined annotation CSVs into stages + events.

CAISR (Complete AI Sleep Report) emits a combined annotation table sampled at
2 Hz with integer-coded columns for ``stage``, ``arousal``, ``resp`` and
``limb`` (see github.com/bdsp-core/CAISR-App). Because code conventions can
vary between CAISR releases, the mappings below are overridable via environment
variables so downstream users can align them with the exact model output.
"""

from __future__ import annotations

import csv
import io
import os
from typing import Optional

from .events import (
    CAT_APNEA_CENTRAL,
    CAT_APNEA_MIXED,
    CAT_APNEA_OBSTRUCTIVE,
    CAT_AROUSAL,
    CAT_HYPOPNEA,
    CAT_LIMB,
    CAT_RERA,
    ScoredEvent,
)

# Default CAISR integer code maps (override via env when needed).
_DEFAULT_STAGE_MAP = {5: "W", 4: "REM", 3: "N1", 2: "N2", 1: "N3", 0: "?", -1: "?"}
_DEFAULT_RESP_MAP = {
    1: (CAT_APNEA_OBSTRUCTIVE, "Obstructive apnea"),
    2: (CAT_APNEA_CENTRAL, "Central apnea"),
    3: (CAT_APNEA_MIXED, "Mixed apnea"),
    4: (CAT_HYPOPNEA, "Hypopnea"),
    5: (CAT_RERA, "RERA"),
}
_DEFAULT_LIMB_MAP = {1: "Isolated limb movement", 2: "Periodic limb movement"}


def _parse_map_env(name: str) -> Optional[dict]:
    raw = os.environ.get(name)
    if not raw:
        return None
    out: dict = {}
    for pair in raw.split(","):
        if ":" not in pair:
            continue
        k, v = pair.split(":", 1)
        try:
            out[int(k.strip())] = v.strip()
        except ValueError:
            continue
    return out or None


def _stage_map() -> dict:
    override = _parse_map_env("HSP_CAISR_STAGE_MAP")
    if not override:
        return _DEFAULT_STAGE_MAP
    return {int(k): v for k, v in override.items()}


def _to_int(value) -> Optional[int]:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def parse_caisr_csv(text: str, fs: float = 2.0, epoch_sec: float = 30.0):
    """Parse CAISR combined annotations text into (stage_epochs, events).

    Returns a tuple ``(stage_epochs, events)`` compatible with the rest of the
    pipeline (``compute_metrics`` etc.).
    """
    reader = csv.DictReader(io.StringIO(text))
    fields = {f.lower(): f for f in (reader.fieldnames or [])}

    stage_col = fields.get("stage")
    resp_col = fields.get("resp") or fields.get("respiratory")
    arousal_col = fields.get("arousal")
    limb_col = fields.get("limb")

    stage_map = _stage_map()
    samples_per_epoch = int(round(fs * epoch_sec))

    stage_samples: list[str] = []
    resp_series: list[Optional[int]] = []
    arousal_series: list[int] = []
    limb_series: list[Optional[int]] = []

    for row in reader:
        if stage_col:
            code = _to_int(row.get(stage_col))
            stage_samples.append(stage_map.get(code, "?") if code is not None else "?")
        if resp_col:
            resp_series.append(_to_int(row.get(resp_col)))
        if arousal_col:
            arousal_series.append(_to_int(row.get(arousal_col)) or 0)
        if limb_col:
            limb_series.append(_to_int(row.get(limb_col)))

    # Downsample stage to 30 s epochs by majority vote.
    stage_epochs: list[str] = []
    for i in range(0, len(stage_samples), samples_per_epoch):
        window = stage_samples[i : i + samples_per_epoch]
        if not window:
            break
        stage_epochs.append(max(set(window), key=window.count))

    events: list[ScoredEvent] = []
    events += _runs_to_events(resp_series, fs, kind="resp")
    events += _runs_to_events(arousal_series, fs, kind="arousal")
    events += _runs_to_events(limb_series, fs, kind="limb")
    return stage_epochs, events


def _runs_to_events(series: list, fs: float, kind: str) -> list[ScoredEvent]:
    if not series:
        return []
    events: list[ScoredEvent] = []
    n = len(series)
    i = 0
    while i < n:
        code = series[i]
        if not code:  # 0 or None
            i += 1
            continue
        j = i
        while j < n and series[j] == code:
            j += 1
        onset = i / fs
        duration = (j - i) / fs
        if kind == "resp":
            mapped = _DEFAULT_RESP_MAP.get(code)
            if mapped:
                events.append(ScoredEvent(onset, duration, mapped[0], mapped[1]))
        elif kind == "arousal":
            events.append(ScoredEvent(onset, duration, CAT_AROUSAL, "Arousal"))
        elif kind == "limb":
            sub = _DEFAULT_LIMB_MAP.get(code, "Limb movement")
            events.append(ScoredEvent(onset, duration, CAT_LIMB, sub))
        i = j
    return events
