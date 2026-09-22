"""SpO2 waveform helpers: nadir, ODI, and per-event desaturation coupling.

Used when CAISR (or human CSVs) omit nadir metadata but a SpO2 channel is
available in the source EDF or a downsampled ``signals.json`` preview.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

from .events import (
    APNEA_CATEGORIES,
    CAT_HYPOPNEA,
    CAT_RERA,
    ScoredEvent,
)


def spo2_nadir(samples: Sequence[float], *, min_valid: float = 50.0, max_valid: float = 100.0) -> Optional[float]:
    """Lowest physiologically plausible SpO2 in the trace."""
    vals = [float(v) for v in samples if min_valid <= float(v) <= max_valid]
    if not vals:
        return None
    return round(min(vals), 1)


def desaturation_events(
    samples: Sequence[float],
    fs: float,
    *,
    drop_pct: float = 3.0,
    min_dur_sec: float = 2.0,
    baseline_sec: float = 60.0,
) -> list[tuple[float, float, float]]:
    """Detect SpO2 drops ≥ ``drop_pct`` lasting ≥ ``min_dur_sec``.

    Returns list of ``(onset_sec, duration_sec, nadir)``.
    Simple rolling-baseline detector — good enough for ODI / event coupling.
    """
    if fs <= 0 or len(samples) < int(fs * 5):
        return []
    n = len(samples)
    win = max(1, int(baseline_sec * fs))
    min_len = max(1, int(min_dur_sec * fs))
    out: list[tuple[float, float, float]] = []
    i = win
    while i < n:
        # local baseline = median-ish of prior window (use mean of sorted mid)
        window = [float(samples[j]) for j in range(i - win, i) if 50 <= float(samples[j]) <= 100]
        if len(window) < win // 3:
            i += 1
            continue
        window.sort()
        baseline = window[len(window) // 2]
        v = float(samples[i])
        if not (50 <= v <= 100) or baseline - v < drop_pct:
            i += 1
            continue
        # extend while still ≥ drop_pct below baseline (or still falling)
        j = i
        nadir = v
        while j < n:
            vj = float(samples[j])
            if 50 <= vj <= 100:
                nadir = min(nadir, vj)
            if baseline - vj < drop_pct * 0.5 and j - i >= min_len:
                break
            if j - i > int(120 * fs):
                break
            j += 1
        if j - i >= min_len and baseline - nadir >= drop_pct:
            out.append((i / fs, (j - i) / fs, round(nadir, 1)))
            i = j
        else:
            i += 1
    return out


def odi_from_trace(samples: Sequence[float], fs: float, tst_hours: float) -> tuple[Optional[float], int]:
    """Oxygen desaturation index (events/h TST) from a SpO2 waveform."""
    events = desaturation_events(samples, fs)
    n = len(events)
    if tst_hours is None or tst_hours <= 0:
        return None, n
    return round(n / tst_hours, 1), n


def enrich_events_with_spo2(
    events: Iterable[ScoredEvent],
    samples: Sequence[float],
    fs: float,
    *,
    search_after_sec: float = 45.0,
) -> list[ScoredEvent]:
    """Attach ``nadir_spo2`` to respiratory events from the waveform."""
    resp_cats = set(APNEA_CATEGORIES) | {CAT_HYPOPNEA, CAT_RERA}
    out: list[ScoredEvent] = []
    for e in events:
        if e.category not in resp_cats or e.nadir_spo2 is not None or fs <= 0:
            out.append(e)
            continue
        start = int(max(0, e.onset_sec * fs))
        end = int(min(len(samples), (e.onset_sec + e.duration_sec + search_after_sec) * fs))
        if end <= start:
            out.append(e)
            continue
        window = [float(samples[i]) for i in range(start, end) if 50 <= float(samples[i]) <= 100]
        if not window:
            out.append(e)
            continue
        nadir = round(min(window), 1)
        out.append(
            ScoredEvent(
                onset_sec=e.onset_sec,
                duration_sec=e.duration_sec,
                category=e.category,
                subtype=e.subtype,
                nadir_spo2=nadir,
                raw=e.raw,
            )
        )
    return out


def apply_spo2_to_metrics(metrics: dict, samples: Sequence[float], fs: float) -> dict:
    """Fill ``spo2_nadir`` / ``odi`` / ``n_desaturations`` when missing."""
    m = dict(metrics)
    nadir = spo2_nadir(samples)
    if nadir is not None and m.get("spo2_nadir") is None:
        m["spo2_nadir"] = nadir
    tst_min = m.get("total_sleep_time_min") or 0.0
    tst_h = float(tst_min) / 60.0 if tst_min else 0.0
    # Only compute ODI when we have usable TST for an index.
    if m.get("index_valid", True) and tst_h > 0 and (m.get("odi") is None or m.get("n_desaturations", 0) == 0):
        odi, n = odi_from_trace(samples, fs, tst_h)
        if odi is not None:
            m["odi"] = odi
            m["n_desaturations"] = n
    elif m.get("spo2_nadir") is None and nadir is not None:
        m["spo2_nadir"] = nadir
    return m
