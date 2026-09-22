"""Parsing of HSP human-scored annotation CSVs into stages and clinical events.

The BIDS human annotation file has columns: ``epoch,time,duration,event``.
``time`` is a clock time (HH:MM:SS) that rolls over midnight. ``event`` is a
free-text label following the scoring software's conventions, e.g.::

    Sleep_stage_W / Sleep_stage_N1 / Sleep_stage_N2 / Sleep_stage_N3 /
    Sleep_stage_REM / Sleep_stage_?
    Respiratory Event - Obstructive Apnea - Desat 89.0 %
    Respiratory Event - Central Apnea
    Respiratory Event - Mixed Apnea
    Respiratory Event - Hypopnea - Desat 93.0 %
    Respiratory Event - RERA
    * Arousal - Spontaneous / * Arousal - Respiratory Event / * Arousal - PLM
    PLM - Isolated / PLM - Periodic
    Position - Supine / Left / Right / Prone
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Optional

# Canonical stage vocabulary used throughout the app.
STAGE_ORDER = ["W", "N1", "N2", "N3", "REM"]
STAGE_UNKNOWN = "?"

_STAGE_LABELS = {
    "sleep_stage_w": "W",
    "sleep_stage_wake": "W",
    "sleep_stage_n1": "N1",
    "sleep_stage_n2": "N2",
    "sleep_stage_n3": "N3",
    "sleep_stage_n4": "N3",  # legacy R&K stage 4 folded into N3
    "sleep_stage_r": "REM",
    "sleep_stage_rem": "REM",
    "sleep_stage_?": STAGE_UNKNOWN,
}


def stage_from_label(label: str) -> Optional[str]:
    """Return canonical stage for a stage label, or None if not a stage label."""
    key = label.strip().lower()
    if key in _STAGE_LABELS:
        return _STAGE_LABELS[key]
    if key.startswith("sleep_stage_"):
        return STAGE_UNKNOWN
    return None


# Event categories the dashboard cares about.
CAT_APNEA_OBSTRUCTIVE = "apnea_obstructive"
CAT_APNEA_CENTRAL = "apnea_central"
CAT_APNEA_MIXED = "apnea_mixed"
CAT_HYPOPNEA = "hypopnea"
CAT_RERA = "rera"
CAT_AROUSAL = "arousal"
CAT_LIMB = "limb_movement"
CAT_DESAT = "desaturation"
CAT_POSITION = "position"

RESPIRATORY_EVENT_CATEGORIES = {
    CAT_APNEA_OBSTRUCTIVE,
    CAT_APNEA_CENTRAL,
    CAT_APNEA_MIXED,
    CAT_HYPOPNEA,
    CAT_RERA,
}
APNEA_CATEGORIES = {CAT_APNEA_OBSTRUCTIVE, CAT_APNEA_CENTRAL, CAT_APNEA_MIXED}

_DESAT_RE = re.compile(r"desat\D*(\d{1,3}(?:\.\d+)?)\s*%", re.IGNORECASE)
_LOWO2_RE = re.compile(r"low\s*o2\s*[:=]?\s*(\d{1,3}(?:\.\d+)?)", re.IGNORECASE)


@dataclass
class ScoredEvent:
    onset_sec: float
    duration_sec: float
    category: str
    subtype: str = ""
    nadir_spo2: Optional[float] = None
    raw: str = ""


@dataclass
class ParsedAnnotations:
    start_clock: Optional[str]
    epoch_length_sec: float
    stage_epochs: list[str] = field(default_factory=list)  # index 0 == epoch 1
    events: list[ScoredEvent] = field(default_factory=list)
    n_raw_rows: int = 0


def classify_event(label: str) -> Optional[tuple[str, str]]:
    """Map a raw event label to (category, subtype). None for non-clinical rows."""
    text = label.strip()
    low = text.lower()

    if low.startswith("sleep_stage_"):
        return None

    # Harmonized single-token labels (e.g. I0003 "Standardised Event" column).
    compact = re.sub(r"[^a-z]", "", low)
    if compact in ("obstructiveapnea", "oa"):
        return CAT_APNEA_OBSTRUCTIVE, "Obstructive apnea"
    if compact in ("centralapnea", "ca"):
        return CAT_APNEA_CENTRAL, "Central apnea"
    if compact in ("mixedapnea", "ma"):
        return CAT_APNEA_MIXED, "Mixed apnea"
    if compact in ("hypopnea", "hyp", "hypopnoea"):
        return CAT_HYPOPNEA, "Hypopnea"
    if compact in ("rera", "resparousal"):
        return CAT_RERA, "RERA"
    if compact in ("arousal", "microarousal", "eegarousal", "spontaneousarousal"):
        return CAT_AROUSAL, "Arousal"
    if compact in ("limbmvt", "limbmovement", "legmovement", "lm", "plm", "plms"):
        return CAT_LIMB, "Limb movement"
    if compact in ("desaturation", "desat"):
        return CAT_DESAT, "Desaturation"

    # Microarousal free-text (I0002): "Microarousal [Hypopnea][PLMS]" etc.
    if "microarousal" in low or "micro arousal" in low:
        if "resp" in low or "hypopnea" in low or "apnea" in low:
            return CAT_AROUSAL, "Respiratory arousal"
        if "plm" in low or "lm]" in low or "limb" in low:
            return CAT_AROUSAL, "Limb arousal"
        if "spon" in low:
            return CAT_AROUSAL, "Spontaneous arousal"
        return CAT_AROUSAL, "Arousal"

    # Leg / limb movement free-text (I0002): "Leg Movement (in PLMS)".
    if "leg movement" in low or "limb movement" in low:
        if "plm" in low:
            return CAT_LIMB, "Periodic limb movement"
        return CAT_LIMB, "Limb movement"

    if "respiratory event" in low or "resp event" in low:
        if "obstructive apnea" in low or "obstructive_apnea" in low:
            return CAT_APNEA_OBSTRUCTIVE, "Obstructive apnea"
        if "central apnea" in low:
            return CAT_APNEA_CENTRAL, "Central apnea"
        if "mixed apnea" in low:
            return CAT_APNEA_MIXED, "Mixed apnea"
        if "hypopnea" in low:
            return CAT_HYPOPNEA, "Hypopnea"
        if "rera" in low:
            return CAT_RERA, "RERA"
        if "apnea" in low:
            return CAT_APNEA_OBSTRUCTIVE, "Apnea (unspecified)"
        return CAT_HYPOPNEA, "Respiratory event"

    # Standalone apnea/hypopnea labels (some sites don't prefix "Respiratory Event")
    if low.startswith("obstructive apnea"):
        return CAT_APNEA_OBSTRUCTIVE, "Obstructive apnea"
    if low.startswith("central apnea"):
        return CAT_APNEA_CENTRAL, "Central apnea"
    if low.startswith("mixed apnea"):
        return CAT_APNEA_MIXED, "Mixed apnea"
    if low.startswith("hypopnea"):
        return CAT_HYPOPNEA, "Hypopnea"

    if "arousal" in low:
        if "respiratory" in low:
            return CAT_AROUSAL, "Respiratory arousal"
        if "plm" in low or "limb" in low:
            return CAT_AROUSAL, "Limb arousal"
        if "spontaneous" in low:
            return CAT_AROUSAL, "Spontaneous arousal"
        return CAT_AROUSAL, "Arousal"

    if low.startswith("plm") or "limb movement" in low or "leg movement" in low:
        if "periodic" in low:
            return CAT_LIMB, "Periodic limb movement"
        if "isolated" in low:
            return CAT_LIMB, "Isolated limb movement"
        return CAT_LIMB, "Limb movement"

    if "desaturation" in low or ("desat" in low and "arousal" not in low and "respiratory" not in low):
        return CAT_DESAT, "Desaturation"

    if low.startswith("position"):
        return CAT_POSITION, text.split("-", 1)[-1].strip() or "Position"

    return None


def _extract_nadir(label: str) -> Optional[float]:
    """Best-effort SpO2 nadir from an event label.

    Handles two conventions: S0001 "Desat 93.0 %" (the number *is* the nadir)
    and I0002 "Desaturation 4%, Low O2: 88" (nadir is the Low O2 value).
    """
    low = _LOWO2_RE.search(label)
    if low:
        try:
            val = float(low.group(1))
            if val >= 40:  # guard "Low O2: 0" artifacts
                return val
        except ValueError:
            pass
    m = _DESAT_RE.search(label)
    if m:
        try:
            val = float(m.group(1))
            # A tiny value is a desaturation *drop*, not an absolute nadir.
            return val if val >= 40 else None
        except ValueError:
            return None
    return None


def _parse_clock(value: str) -> Optional[int]:
    """Return seconds-of-day for an HH:MM:SS[.f] clock string."""
    value = value.strip()
    if not value:
        return None
    parts = value.split(":")
    if len(parts) < 3:
        return None
    try:
        h = int(parts[0])
        m = int(parts[1])
        s = float(parts[2])
    except ValueError:
        return None
    return int(round(h * 3600 + m * 60 + s))


def parse_annotations_csv(text: str) -> ParsedAnnotations:
    """Parse the raw human annotation CSV text into stages + events.

    Times are converted to seconds relative to the recording start, handling
    a single midnight rollover monotonically.
    """
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    start_sod: Optional[int] = None
    prev_sod: Optional[int] = None
    day_offset = 0
    start_clock: Optional[str] = None

    stage_by_epoch: dict[int, str] = {}
    events: list[ScoredEvent] = []
    max_epoch = 0

    for row in rows:
        label = (row.get("event") or "").strip()
        if not label:
            continue
        clock = (row.get("time") or "").strip()
        sod = _parse_clock(clock)

        onset_sec: Optional[float] = None
        if sod is not None:
            if start_sod is None:
                start_sod = sod
                prev_sod = sod
                start_clock = clock.split(".")[0]
            else:
                if sod < prev_sod - 1:  # rollover past midnight
                    day_offset += 86400
                prev_sod = sod
            onset_sec = float(sod + day_offset - start_sod)

        try:
            duration = float(row.get("duration") or 0.0)
        except ValueError:
            duration = 0.0

        stage = stage_from_label(label)
        if stage is not None:
            try:
                epoch = int(float(row.get("epoch") or 0))
            except ValueError:
                epoch = 0
            if epoch <= 0 and onset_sec is not None:
                epoch = int(onset_sec // 30) + 1
            if epoch > 0:
                stage_by_epoch[epoch] = stage
                max_epoch = max(max_epoch, epoch)
            continue

        classified = classify_event(label)
        if classified is None:
            continue
        category, subtype = classified
        if onset_sec is None:
            continue
        events.append(
            ScoredEvent(
                onset_sec=onset_sec,
                duration_sec=duration,
                category=category,
                subtype=subtype,
                nadir_spo2=_extract_nadir(label),
                raw=label,
            )
        )

    stage_epochs: list[str] = []
    if max_epoch > 0:
        stage_epochs = [stage_by_epoch.get(i, STAGE_UNKNOWN) for i in range(1, max_epoch + 1)]

    return ParsedAnnotations(
        start_clock=start_clock,
        epoch_length_sec=30.0,
        stage_epochs=stage_epochs,
        events=events,
        n_raw_rows=len(rows),
    )
