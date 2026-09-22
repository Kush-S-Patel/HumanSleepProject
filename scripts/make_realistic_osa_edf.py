"""Generate a CAISR-detectable synthetic PSG with a mild OSA profile.

Targets (mirroring a typical mild adult diagnostic PSG)::

    ~15 obstructive apneas, ~7 central, ~22 hypopneas  → AHI ≈ 6.4 /h
    SpO2 nadir ≈ 88%, ~20 desaturations
    ~8 h recording, ~6.9 h intended sleep

CAISR resp (rule-based) needs *relative* ventilation drops vs a lagged
envelope, not decorative sinusoids:

  * hypopnea  : ptaf amplitude × ~0.45 for ≥ 10 s + SpO2 drop ≥ 3%
  * apnea     : ptaf amplitude × ~0.15 for ≥ 10 s (effort kept = obstructive;
                effort also dropped = central)
  * events mid-recording with recovery breaths after each drop

Channels use CAISR-canonical names at 200 Hz. Pure stdlib (no numpy).

Usage::

    python scripts/make_realistic_osa_edf.py [out.edf]
"""

from __future__ import annotations

import math
import os
import random
import sys
from array import array

# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------
FS = 200
DURATION_SEC = 8 * 3600  # 8 h
N = DURATION_SEC * FS

# Intended sleep window (CAISR staging may approximate this)
SLEEP_START = 25 * 60  # lights-out + latency
SLEEP_END = SLEEP_START + int(6.9 * 3600)

BREATH_HZ = 0.25  # 15 breaths/min


# ---------------------------------------------------------------------------
# Event schedule matching the real mild-OSA profile
# ---------------------------------------------------------------------------
def _build_events(rng: random.Random) -> list[dict]:
    """Return timed respiratory events with coupled desaturations.

    Counts: 15 OA, 7 CA, 22 hypopnea. Extra REM-window clustering.
    """
    events: list[dict] = []

    # Quiet NREM-ish windows and REM-ish clusters (seconds from t0).
    # REM windows get denser events (target elevated REM AHI).
    nrem_windows = [
        (SLEEP_START + 20 * 60, SLEEP_START + 90 * 60),
        (SLEEP_START + 110 * 60, SLEEP_START + 170 * 60),
        (SLEEP_START + 250 * 60, SLEEP_START + 300 * 60),
        (SLEEP_START + 360 * 60, SLEEP_START + 400 * 60),
    ]
    rem_windows = [
        (SLEEP_START + 95 * 60, SLEEP_START + 115 * 60),
        (SLEEP_START + 185 * 60, SLEEP_START + 215 * 60),
        (SLEEP_START + 310 * 60, SLEEP_START + 345 * 60),
        (SLEEP_START + 405 * 60, min(SLEEP_END - 5 * 60, DURATION_SEC - 5 * 60)),
    ]

    # (kind, count, prefer_rem_fraction)
    plan = [
        ("obstructive", 15, 0.45),
        ("central", 7, 0.25),
        ("hypopnea", 22, 0.40),
    ]

    used: list[tuple[float, float]] = []

    def _overlaps(a: float, b: float) -> bool:
        for s, e in used:
            if not (b < s - 8 or a > e + 8):
                return True
        return False

    def _pick(windows: list[tuple[float, float]]) -> float:
        for _ in range(200):
            w0, w1 = windows[rng.randrange(len(windows))]
            t = rng.uniform(w0, w1 - 25)
            dur = rng.uniform(10.0, 22.0)
            if not _overlaps(t, t + dur):
                return t, dur
        # fallback: sequential placement
        t = used[-1][1] + 30 if used else SLEEP_START + 600
        return t, 12.0

    for kind, count, rem_frac in plan:
        n_rem = int(round(count * rem_frac))
        n_nrem = count - n_rem
        for i in range(count):
            prefer_rem = i < n_rem
            wins = rem_windows if prefer_rem else nrem_windows
            t, dur = _pick(wins)
            # Severity / SpO2 coupling
            if kind == "hypopnea":
                flow_scale = rng.uniform(0.38, 0.50)  # ~50-62% drop
                effort_scale = rng.uniform(0.85, 1.05)
                spo2_drop = rng.uniform(3.2, 5.5)
            elif kind == "obstructive":
                flow_scale = rng.uniform(0.08, 0.18)  # ≥80% drop
                effort_scale = rng.uniform(0.75, 1.10)  # effort maintained
                spo2_drop = rng.uniform(4.0, 7.5)
            else:  # central
                flow_scale = rng.uniform(0.08, 0.18)
                effort_scale = rng.uniform(0.05, 0.18)  # effort also gone
                spo2_drop = rng.uniform(3.5, 6.5)

            # Force one event to hit nadir 88% (baseline 96 → drop 8)
            events.append(
                {
                    "kind": kind,
                    "t0": t,
                    "dur": dur,
                    "flow_scale": flow_scale,
                    "effort_scale": effort_scale,
                    "spo2_drop": spo2_drop,
                    "remish": prefer_rem,
                }
            )
            used.append((t, t + dur))

    # Guarantee nadir ≈ 88%: deepen the largest planned desat.
    events.sort(key=lambda e: e["t0"])
    deepest = max(events, key=lambda e: e["spo2_drop"])
    deepest["spo2_drop"] = 8.0  # 96 → 88

    return events


# ---------------------------------------------------------------------------
# Signal synthesis
# ---------------------------------------------------------------------------
def _sin(i: int, hz: float, phase: float = 0.0) -> float:
    return math.sin(2 * math.pi * hz * (i / FS) + phase)


def _envelope(i: int, events: list[dict], which: str) -> float:
    """Multiplicative envelope (1.0 = eupnea) for flow or effort."""
    t = i / FS
    scale = 1.0
    for e in events:
        t0, t1 = e["t0"], e["t0"] + e["dur"]
        if t0 <= t <= t1:
            # raised-cosine edges (~0.6 s) so envelope detectors see a clean drop
            edge = 0.6
            u = t - t0
            if u < edge:
                fade = 0.5 * (1 - math.cos(math.pi * u / edge))
            elif t1 - t < edge:
                fade = 0.5 * (1 - math.cos(math.pi * (t1 - t) / edge))
            else:
                fade = 1.0
            target = e["flow_scale"] if which == "flow" else e["effort_scale"]
            scale = 1.0 + fade * (target - 1.0)
            break
    return scale


def _spo2_at(i: int, events: list[dict], baseline: float = 96.0) -> float:
    """SpO2 with desats starting near event end, lasting ~12-20 s, then recover."""
    t = i / FS
    val = baseline
    for e in events:
        # Desat begins ~2 s before event end, trough ~6 s after end, recover by +20 s
        start = e["t0"] + e["dur"] - 2.0
        trough = e["t0"] + e["dur"] + 6.0
        end = e["t0"] + e["dur"] + 18.0
        drop = e["spo2_drop"]
        if start <= t <= trough:
            frac = (t - start) / max(trough - start, 0.1)
            val = min(val, baseline - drop * frac)
        elif trough < t <= end:
            frac = (t - trough) / max(end - trough, 0.1)
            val = min(val, baseline - drop * (1.0 - frac))
    # light noise
    val += random.uniform(-0.15, 0.15)
    return max(60.0, min(100.0, val))


def _eeg_sample(i: int, band_hz: float, amp: float, rng_noise: float) -> float:
    return amp * _sin(i, band_hz) + rng_noise


def synthesize(events: list[dict], seed: int = 42) -> dict[str, array]:
    rng = random.Random(seed)
    random.seed(seed)

    chans = {
        "f3-m2": array("f"),
        "f4-m1": array("f"),
        "c3-m2": array("f"),
        "c4-m1": array("f"),
        "o1-m2": array("f"),
        "o2-m1": array("f"),
        "e1-m2": array("f"),
        "e2-m1": array("f"),
        "chin1-chin2": array("f"),
        "abd": array("f"),
        "chest": array("f"),
        "spo2": array("f"),
        "ecg": array("f"),
        "lat": array("f"),
        "rat": array("f"),
        "airflow": array("f"),
        "ptaf": array("f"),
        "hr": array("f"),
        "position": array("f"),
    }

    # Pre-size via extend in chunks for speed
    chunk = 2000
    for start in range(0, N, chunk):
        end = min(N, start + chunk)
        buf = {k: [] for k in chans}
        for i in range(start, end):
            t = i / FS
            # Intended stage band for EEG flavour (helps staging look sleep-like)
            if t < SLEEP_START or t > SLEEP_END:
                # wake: alpha-ish
                eeg_hz, eeg_amp = 10.0, 25.0
                chin_amp = 40.0
            else:
                # crude REM islands matching rem_windows density
                in_rem = any(
                    (SLEEP_START + a) <= t <= (SLEEP_START + b)
                    for a, b in [
                        (95 * 60, 115 * 60),
                        (185 * 60, 215 * 60),
                        (310 * 60, 345 * 60),
                        (405 * 60, 430 * 60),
                    ]
                )
                if in_rem:
                    eeg_hz, eeg_amp = 7.0, 18.0  # theta
                    chin_amp = 8.0
                elif (t - SLEEP_START) % 3600 < 900:
                    eeg_hz, eeg_amp = 1.2, 45.0  # delta / N3-ish bursts
                    chin_amp = 15.0
                else:
                    eeg_hz, eeg_amp = 13.0, 20.0  # spindle-ish N2
                    chin_amp = 18.0

            n = rng.uniform(-3, 3)
            for name, phase in (
                ("f3-m2", 0.0),
                ("f4-m1", 0.2),
                ("c3-m2", 0.4),
                ("c4-m1", 0.55),
                ("o1-m2", 0.7),
                ("o2-m1", 0.85),
            ):
                buf[name].append(_eeg_sample(i, eeg_hz, eeg_amp, n) + 2 * _sin(i, eeg_hz * 0.5, phase))

            buf["e1-m2"].append(12 * _sin(i, 0.3, 0.0) + rng.uniform(-2, 2))
            buf["e2-m1"].append(12 * _sin(i, 0.3, 0.4) + rng.uniform(-2, 2))
            buf["chin1-chin2"].append(chin_amp * _sin(i, 60.0) * 0.05 + rng.uniform(-chin_amp * 0.1, chin_amp * 0.1))

            flow_env = _envelope(i, events, "flow")
            eff_env = _envelope(i, events, "effort")
            # Nasal pressure (ptaf): primary CAISR breathing_trace — sharp drops matter
            breath = _sin(i, BREATH_HZ)
            ptaf = 1.2 * breath * flow_env + rng.uniform(-0.03, 0.03)
            airflow = 0.9 * breath * flow_env + rng.uniform(-0.03, 0.03)
            # Effort belts: keep amplitude for obstructive; drop for central
            chest = 0.8 * _sin(i, BREATH_HZ, 0.15) * eff_env + rng.uniform(-0.02, 0.02)
            abd = 0.75 * _sin(i, BREATH_HZ, 0.35) * eff_env + rng.uniform(-0.02, 0.02)

            buf["ptaf"].append(ptaf)
            buf["airflow"].append(airflow)
            buf["chest"].append(chest)
            buf["abd"].append(abd)
            buf["spo2"].append(_spo2_at(i, events))

            # Simple ECG / HR / position / limbs
            hr_bpm = 62 + 6 * math.sin(2 * math.pi * t / 3600)
            buf["ecg"].append(0.8 * _sin(i, hr_bpm / 60.0) + rng.uniform(-0.05, 0.05))
            buf["hr"].append(hr_bpm)
            # mostly supine (0) with some side (90) — mild supine predominance
            buf["position"].append(0.0 if (t // 1800) % 3 else 90.0)
            buf["lat"].append(rng.uniform(-5, 5))
            buf["rat"].append(rng.uniform(-5, 5))

        for k, vals in buf.items():
            chans[k].extend(vals)

    return chans


# ---------------------------------------------------------------------------
# EDF writer (16-bit, 1-second records)
# ---------------------------------------------------------------------------
PHYS = {
    "f3-m2": (-200, 200),
    "f4-m1": (-200, 200),
    "c3-m2": (-200, 200),
    "c4-m1": (-200, 200),
    "o1-m2": (-200, 200),
    "o2-m1": (-200, 200),
    "e1-m2": (-200, 200),
    "e2-m1": (-200, 200),
    "chin1-chin2": (-100, 100),
    "abd": (-2, 2),
    "chest": (-2, 2),
    "spo2": (50, 100),
    "ecg": (-2, 2),
    "lat": (-100, 100),
    "rat": (-100, 100),
    "airflow": (-2, 2),
    "ptaf": (-2, 2),
    "hr": (20, 180),
    "position": (0, 360),
}

ORDER = [
    "f3-m2", "f4-m1", "c3-m2", "c4-m1", "o1-m2", "o2-m1",
    "e1-m2", "e2-m1", "chin1-chin2",
    "abd", "chest", "spo2", "ecg", "lat", "rat",
    "airflow", "ptaf", "hr", "position",
]


def _fit16(label: str) -> bytes:
    return f"{label:<16.16s}".encode("ascii", "replace")


def write_edf(path: str, chans: dict[str, array]) -> None:
    ns = len(ORDER)
    ndr = DURATION_SEC  # 1-second records
    header_bytes = 256 * (ns + 1)

    # Fixed header
    top = bytearray(256)
    top[0:8] = b"0       "
    top[8:88] = f"{'X X Synthetic Mild OSA':<80s}".encode("ascii")
    top[88:168] = f"{'Startdate 01-JAN-2026 Realistic OS A demo':<80s}".encode("ascii")
    top[168:184] = b"01.01.2622.00.00"
    top[184:192] = f"{header_bytes:<8d}".encode("ascii")
    top[192:236] = b" " * 44
    top[236:244] = f"{ndr:<8d}".encode("ascii")
    top[244:252] = f"{1:<8d}".encode("ascii")
    top[252:256] = f"{ns:<4d}".encode("ascii")

    # Per-signal headers
    labels = b"".join(_fit16(n) for n in ORDER)
    transducers = b"".join(f"{'':<80s}".encode("ascii") for _ in ORDER)
    dims = []
    for n in ORDER:
        unit = "%" if n == "spo2" else ("deg" if n == "position" else ("BPM" if n == "hr" else "uV" if "m" in n or n.startswith(("f", "c", "o", "e", "chin")) else "mV"))
        if n in ("abd", "chest", "airflow", "ptaf", "ecg"):
            unit = "uV"
        if n in ("lat", "rat", "chin1-chin2"):
            unit = "uV"
        dims.append(f"{unit:<8.8s}".encode("ascii"))
    dims_b = b"".join(dims)

    physmin = b"".join(f"{PHYS[n][0]:<8.8g}".encode("ascii") for n in ORDER)
    physmax = b"".join(f"{PHYS[n][1]:<8.8g}".encode("ascii") for n in ORDER)
    digmin = b"".join(f"{-32768:<8d}".encode("ascii") for _ in ORDER)
    digmax = b"".join(f"{32767:<8d}".encode("ascii") for _ in ORDER)
    prefilter = b"".join(f"{'':<80s}".encode("ascii") for _ in ORDER)
    nsamps = b"".join(f"{FS:<8d}".encode("ascii") for _ in ORDER)
    reserved = b"".join(b" " * 32 for _ in ORDER)

    with open(path, "wb") as out:
        out.write(top)
        out.write(labels)
        out.write(transducers)
        out.write(dims_b)
        out.write(physmin)
        out.write(physmax)
        out.write(digmin)
        out.write(digmax)
        out.write(prefilter)
        out.write(nsamps)
        out.write(reserved)

        # Data records
        for r in range(ndr):
            i0 = r * FS
            i1 = i0 + FS
            for n in ORDER:
                pmin, pmax = PHYS[n]
                scale = (32767 - (-32768)) / (pmax - pmin)
                samples = chans[n][i0:i1]
                dig = array("h")
                for v in samples:
                    d = int(round((v - pmin) * scale + (-32768)))
                    if d < -32768:
                        d = -32768
                    elif d > 32767:
                        d = 32767
                    dig.append(d)
                out.write(dig.tobytes())


def main() -> None:
    out = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.path.join(os.path.expanduser("~"), "Downloads", "synthetic_mild_osa_caisr.edf")
    )
    print(f"Building event schedule…")
    rng = random.Random(42)
    events = _build_events(rng)
    counts = {}
    for e in events:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    print(f"  events: {counts}  (total AHI-events={sum(counts.values())})")
    print(f"  deepest SpO2 drop: {max(e['spo2_drop'] for e in events):.1f} pts (nadir~{96-max(e['spo2_drop'] for e in events):.0f}%)")
    print(f"Synthesizing {DURATION_SEC/3600:.1f} h @ {FS} Hz ({N:,} samples/ch)…")
    chans = synthesize(events, seed=42)
    print(f"Writing {out}…")
    write_edf(out, chans)
    mb = os.path.getsize(out) / (1024 * 1024)
    print(f"Done: {mb:.1f} MB")
    print("Upload this file through the dashboard (or API) to score with CAISR.")


if __name__ == "__main__":
    main()
