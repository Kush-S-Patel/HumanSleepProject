"""Cohort-agnostic annotation parsing.

The five HSP sites store human scoring in markedly different layouts:

* S0001: one combined ``*_task-psg_annotations.csv`` (epoch,time,duration,event)
* I0002: split ``*_sleep_annotations.csv`` (Epoch,...,Stage) +
  ``*_events_annotations.csv`` (Epoch,Stage,...,Time,Length,Description)
* I0003: split ``*_sleepannotations.csv`` (epoch,sleep_stage,...,local_time_start)
  + ``*_eventannotations.csv`` (...,Standardised Event,...,Duration,StampTimeLocal)
* I0006: sparse; when present, matches one of the above.

``parse_study`` accepts whatever annotation files were found for a session and
returns a single normalized :class:`~psg_core.events.ParsedAnnotations`.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Optional

from .events import (
    STAGE_UNKNOWN,
    ParsedAnnotations,
    ScoredEvent,
    _extract_nadir,
    classify_event,
    parse_annotations_csv,
)

# Extra stage aliases used by the split-file cohorts.
_STAGE_WORD = {
    "w": "W",
    "wake": "W",
    "wk": "W",
    "n1": "N1",
    "s1": "N1",
    "stage1": "N1",
    "n2": "N2",
    "s2": "N2",
    "stage2": "N2",
    "n3": "N3",
    "n4": "N3",
    "s3": "N3",
    "s4": "N3",
    "sws": "N3",
    "stage3": "N3",
    "r": "REM",
    "rem": "REM",
    "unscored": STAGE_UNKNOWN,
    "unknown": STAGE_UNKNOWN,
    "none": STAGE_UNKNOWN,
    "l": STAGE_UNKNOWN,  # I0002 "lights"/movement time
    "?": STAGE_UNKNOWN,
    "": STAGE_UNKNOWN,
}


def _canon_stage(value: str) -> str:
    key = str(value).strip().lower()
    if key in _STAGE_WORD:
        return _STAGE_WORD[key]
    # Try numeric AASM codes: 0=W,1=N1,2=N2,3=N3,5=REM (common) else unknown.
    try:
        code = int(float(key))
        return {0: "W", 1: "N1", 2: "N2", 3: "N3", 4: "N3", 5: "REM"}.get(code, STAGE_UNKNOWN)
    except (TypeError, ValueError):
        return STAGE_UNKNOWN


def _read_rows(text: str) -> tuple[list[str], list[dict]]:
    reader = csv.DictReader(io.StringIO(text))
    return (reader.fieldnames or []), list(reader)


def _find(fields: list[str], *candidates: str) -> Optional[str]:
    lower = {f.lower().strip(): f for f in fields}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def _is_combined(fields: list[str]) -> bool:
    fl = {f.lower().strip() for f in fields}
    return "event" in fl and "duration" in fl and ("time" in fl or "epoch" in fl)


def _parse_elapsed_or_clock(value: str) -> Optional[float]:
    """Return seconds for an elapsed (HH:MM:SS from 0) time string."""
    value = str(value).strip()
    if not value or ":" not in value:
        return None
    parts = value.split(":")
    try:
        h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
    except (ValueError, IndexError):
        return None
    return h * 3600 + m * 60 + s


def _parse_dt(value: str) -> Optional[datetime]:
    value = str(value).strip()
    if not value:
        return None
    v = value.replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    return None


def _parse_sleep_file(text: str) -> tuple[list[str], Optional[datetime], Optional[str], int]:
    """Return (stage_epochs, start_dt, start_clock, first_epoch_number)."""
    fields, rows = _read_rows(text)
    epoch_col = _find(fields, "Epoch", "epoch")
    stage_col = _find(fields, "Stage", "sleep_stage", "stage", "SleepStage")
    dt_col = _find(fields, "local_time_start", "StartTime", "utc_time_start")
    if stage_col is None:
        return [], None, None, 1

    stage_by_epoch: dict[int, str] = {}
    dt_by_epoch: dict[int, datetime] = {}
    seq: list[str] = []
    for i, row in enumerate(rows):
        stage = _canon_stage(row.get(stage_col, ""))
        if epoch_col is not None:
            try:
                ep = int(float(row.get(epoch_col) or 0))
            except ValueError:
                ep = i + 1
        else:
            ep = i + 1
        stage_by_epoch[ep] = stage
        if dt_col is not None:
            dt = _parse_dt(row.get(dt_col, ""))
            if dt is not None:
                dt_by_epoch[ep] = dt
        seq.append(stage)

    if not stage_by_epoch:
        return [], None, None, 1

    # Anchor at epoch 1 (lights out); drop pre-recording negative epochs.
    positive = [e for e in stage_by_epoch if e >= 1]
    if positive:
        lo, hi = min(positive), max(positive)
        stage_epochs = [stage_by_epoch.get(e, STAGE_UNKNOWN) for e in range(lo, hi + 1)]
        start_dt = dt_by_epoch.get(lo)
        first_epoch = lo
    else:
        stage_epochs = seq
        start_dt = None
        first_epoch = min(stage_by_epoch)

    start_clock = start_dt.strftime("%H:%M:%S") if start_dt else None
    return stage_epochs, start_dt, start_clock, first_epoch


def _parse_events_file(
    text: str, start_dt: Optional[datetime], epoch_sec: float
) -> list[ScoredEvent]:
    fields, rows = _read_rows(text)
    # Harmonized column first; fall back to free-text when it's unmapped ("x").
    harmonized_col = _find(fields, "Standardised Event", "StandardisedEvent")
    text_col = _find(fields, "Description", "Text", "event", "Event")
    label_col = harmonized_col or text_col
    dur_col = _find(fields, "Duration", "Length", "duration")
    dt_col = _find(fields, "StampTimeLocal", "StampTimeUtc", "local_time_start")
    elapsed_col = _find(fields, "Record Time", "RecordTime")
    epoch_col = _find(fields, "Epoch", "epoch", "DataIndex")

    if label_col is None:
        return []

    events: list[ScoredEvent] = []
    for row in rows:
        label = str(row.get(label_col) or "").strip()
        # If the harmonized value is unmapped, fall back to the free-text label.
        if label.lower() in ("x", "", "log", "-", "none") and text_col and text_col != label_col:
            label = str(row.get(text_col) or "").strip()
        if not label or label.lower() in ("x", "log", "-", "none"):
            continue
        classified = classify_event(label)
        if classified is None:
            continue
        category, subtype = classified

        onset: Optional[float] = None
        if elapsed_col is not None:
            onset = _parse_elapsed_or_clock(row.get(elapsed_col, ""))
        if onset is None and dt_col is not None and start_dt is not None:
            dt = _parse_dt(row.get(dt_col, ""))
            if dt is not None:
                onset = (dt - start_dt).total_seconds()
        if onset is None and epoch_col is not None:
            try:
                ep = int(float(row.get(epoch_col) or 0))
                onset = max(0, (ep - 1)) * epoch_sec
            except ValueError:
                onset = None
        if onset is None:
            onset = 0.0

        dur = 0.0
        if dur_col is not None:
            raw = str(row.get(dur_col) or "").strip()
            dur = _parse_elapsed_or_clock(raw) if ":" in raw else _to_float(raw)

        events.append(
            ScoredEvent(
                onset_sec=float(onset),
                duration_sec=float(dur or 0.0),
                category=category,
                subtype=subtype,
                nadir_spo2=_extract_nadir(label),
                raw=label,
            )
        )
    return events


def _to_float(value: str) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


def parse_study(
    *,
    combined: Optional[str] = None,
    sleep: Optional[str] = None,
    events: Optional[str] = None,
) -> ParsedAnnotations:
    """Parse whatever annotation files exist for a session into one result."""
    # Combined (S0001) file: reuse the dedicated parser.
    if combined is not None:
        return parse_annotations_csv(combined)

    # A single file that happens to be combined-format.
    for candidate in (sleep, events):
        if candidate is not None:
            fields, _ = _read_rows(candidate)
            if _is_combined(fields):
                return parse_annotations_csv(candidate)

    stage_epochs: list[str] = []
    start_dt: Optional[datetime] = None
    start_clock: Optional[str] = None
    if sleep is not None:
        stage_epochs, start_dt, start_clock, _ = _parse_sleep_file(sleep)

    parsed_events: list[ScoredEvent] = []
    if events is not None:
        parsed_events = _parse_events_file(events, start_dt, 30.0)

    return ParsedAnnotations(
        start_clock=start_clock,
        epoch_length_sec=30.0,
        stage_epochs=stage_epochs,
        events=parsed_events,
        n_raw_rows=len(stage_epochs) + len(parsed_events),
    )
