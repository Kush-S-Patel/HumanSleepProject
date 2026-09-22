"""AASM-style sleep metric computation from a hypnogram + scored events."""

from __future__ import annotations

from typing import Iterable, Optional

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
from .hypnogram import SLEEP_STAGES, Hypnogram


def _round(value: Optional[float], ndigits: int = 1) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), ndigits)


# Below this TST, per-hour indices are undefined (tiny denominators explode).
MIN_TST_MIN_FOR_INDEX = 5.0


def _rate_per_hour(count: int, tst_hours: float) -> Optional[float]:
    if tst_hours <= 0:
        return None
    return count / tst_hours


def _event_in_sleep(event: ScoredEvent, stages: list[str], epoch_sec: float) -> bool:
    """True if the event midpoint falls in a sleep epoch (N1/N2/N3/REM)."""
    if epoch_sec <= 0 or not stages:
        return False
    mid = event.onset_sec + max(event.duration_sec, 0.0) / 2.0
    idx = int(mid // epoch_sec)
    if idx < 0 or idx >= len(stages):
        return False
    return stages[idx] in SLEEP_STAGES


def compute_metrics(hyp: Hypnogram, events: Iterable[ScoredEvent]) -> dict:
    """Compute standard sleep-architecture and respiratory indices.

    All time metrics are in minutes; indices are per hour of total sleep time
    (TST). Respiratory/arousal/limb *indices* only count events whose midpoint
    falls in a sleep epoch (AASM-style). Returns a JSON-serializable dict.
    """
    events = list(events)
    epoch_min = hyp.epoch_length_sec / 60.0
    stages = hyp.stages

    n_total = len(stages)
    counts = {"W": 0, "N1": 0, "N2": 0, "N3": 0, "REM": 0}
    for s in stages:
        if s in counts:
            counts[s] += 1

    tst_epochs = counts["N1"] + counts["N2"] + counts["N3"] + counts["REM"]
    tst_min = tst_epochs * epoch_min
    # Guard against near-zero TST (e.g. all-wake AI scoring on noise): indices
    # become undefined rather than astronomically large.
    tst_hours = (tst_min / 60.0) if tst_min >= MIN_TST_MIN_FOR_INDEX else 0.0

    first_sleep, last_sleep = hyp.sleep_bounds()
    first_scored, last_scored = hyp.scored_bounds()

    # Time in bed = scored recording window.
    if first_scored is not None and last_scored is not None:
        tib_epochs = last_scored - first_scored + 1
    else:
        tib_epochs = n_total
    tib_min = tib_epochs * epoch_min

    # Sleep period time (SPT) = first sleep -> last sleep.
    if first_sleep is not None and last_sleep is not None:
        spt_epochs = last_sleep - first_sleep + 1
        waso_epochs = sum(
            1 for s in stages[first_sleep : last_sleep + 1] if s not in SLEEP_STAGES
        )
    else:
        spt_epochs = 0
        waso_epochs = 0
    spt_min = spt_epochs * epoch_min
    waso_min = waso_epochs * epoch_min

    sleep_latency_min = (first_sleep * epoch_min) if first_sleep is not None else None

    rem_latency_min = None
    if first_sleep is not None:
        for i in range(first_sleep, n_total):
            if stages[i] == "REM":
                rem_latency_min = (i - first_sleep) * epoch_min
                break

    sleep_efficiency = (tst_min / tib_min * 100.0) if tib_min > 0 else None

    # Stage-shift based sleep fragmentation index (transitions per hour of sleep).
    transitions = 0
    prev = None
    for s in stages:
        if s == "?":
            continue
        if prev is not None and s != prev:
            transitions += 1
        prev = s
    sfi = _rate_per_hour(transitions, tst_hours)

    # Event tallies — raw counts include wake-time events; indices use sleep-only.
    sleep_events = [e for e in events if _event_in_sleep(e, stages, hyp.epoch_length_sec)]

    n_obstructive = sum(1 for e in events if e.category == CAT_APNEA_OBSTRUCTIVE)
    n_central = sum(1 for e in events if e.category == CAT_APNEA_CENTRAL)
    n_mixed = sum(1 for e in events if e.category == CAT_APNEA_MIXED)
    n_hypopnea = sum(1 for e in events if e.category == CAT_HYPOPNEA)
    n_rera = sum(1 for e in events if e.category == CAT_RERA)
    n_arousal = sum(1 for e in events if e.category == CAT_AROUSAL)
    n_limb = sum(1 for e in events if e.category == CAT_LIMB)

    n_obstructive_s = sum(1 for e in sleep_events if e.category == CAT_APNEA_OBSTRUCTIVE)
    n_central_s = sum(1 for e in sleep_events if e.category == CAT_APNEA_CENTRAL)
    n_mixed_s = sum(1 for e in sleep_events if e.category == CAT_APNEA_MIXED)
    n_apnea_s = n_obstructive_s + n_central_s + n_mixed_s
    n_hypopnea_s = sum(1 for e in sleep_events if e.category == CAT_HYPOPNEA)
    n_rera_s = sum(1 for e in sleep_events if e.category == CAT_RERA)
    n_arousal_s = sum(1 for e in sleep_events if e.category == CAT_AROUSAL)
    n_limb_s = sum(1 for e in sleep_events if e.category == CAT_LIMB)

    ahi = _rate_per_hour(n_apnea_s + n_hypopnea_s, tst_hours)
    rdi = _rate_per_hour(n_apnea_s + n_hypopnea_s + n_rera_s, tst_hours)
    ai = _rate_per_hour(n_apnea_s, tst_hours)
    oai = _rate_per_hour(n_obstructive_s, tst_hours)
    cai = _rate_per_hour(n_central_s, tst_hours)
    hi = _rate_per_hour(n_hypopnea_s, tst_hours)
    arousal_index = _rate_per_hour(n_arousal_s, tst_hours)
    plmi = _rate_per_hour(n_limb_s, tst_hours)

    # SpO2 desaturation summary from event annotations (nadir per event).
    nadirs = [e.nadir_spo2 for e in events if e.nadir_spo2 is not None]
    spo2_nadir = min(nadirs) if nadirs else None
    n_desat_events = sum(1 for e in sleep_events if e.nadir_spo2 is not None)
    odi = _rate_per_hour(n_desat_events, tst_hours)

    def pct_of_tst(stage_epochs: int) -> Optional[float]:
        return (stage_epochs / tst_epochs * 100.0) if tst_epochs > 0 else None

    return {
        "epoch_length_sec": hyp.epoch_length_sec,
        "n_epochs": n_total,
        "n_scored_epochs": tib_epochs,
        # Durations (minutes)
        "time_in_bed_min": _round(tib_min),
        "total_sleep_time_min": _round(tst_min),
        "sleep_period_time_min": _round(spt_min),
        "waso_min": _round(waso_min),
        "sleep_latency_min": _round(sleep_latency_min),
        "rem_latency_min": _round(rem_latency_min),
        "sleep_efficiency_pct": _round(sleep_efficiency),
        # Stage minutes
        "wake_min": _round(counts["W"] * epoch_min),
        "n1_min": _round(counts["N1"] * epoch_min),
        "n2_min": _round(counts["N2"] * epoch_min),
        "n3_min": _round(counts["N3"] * epoch_min),
        "rem_min": _round(counts["REM"] * epoch_min),
        # Stage % of TST
        "n1_pct": _round(pct_of_tst(counts["N1"])),
        "n2_pct": _round(pct_of_tst(counts["N2"])),
        "n3_pct": _round(pct_of_tst(counts["N3"])),
        "rem_pct": _round(pct_of_tst(counts["REM"])),
        # Fragmentation
        "sleep_fragmentation_index": _round(sfi),
        "arousal_index": _round(arousal_index),
        "n_arousals": n_arousal,
        # Respiratory indices
        "ahi": _round(ahi),
        "rdi": _round(rdi),
        "apnea_index": _round(ai),
        "obstructive_apnea_index": _round(oai),
        "central_apnea_index": _round(cai),
        "hypopnea_index": _round(hi),
        "n_obstructive_apnea": n_obstructive,
        "n_central_apnea": n_central,
        "n_mixed_apnea": n_mixed,
        "n_hypopnea": n_hypopnea,
        "n_rera": n_rera,
        # Oxygenation
        "spo2_nadir": _round(spo2_nadir),
        "odi": _round(odi),
        "n_desaturations": n_desat_events,
        # Limb movements
        "plm_index": _round(plmi),
        "n_limb_movements": n_limb,
        # Quality / index validity
        "index_valid": tst_min >= MIN_TST_MIN_FOR_INDEX,
        "n_apnea_hypopnea_in_sleep": n_apnea_s + n_hypopnea_s,
    }
