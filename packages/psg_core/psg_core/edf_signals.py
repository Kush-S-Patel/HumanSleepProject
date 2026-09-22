"""Lightweight EDF signal extraction for dashboard previews (pure stdlib)."""

from __future__ import annotations

import struct
from typing import Optional


def _int(b: bytes) -> int:
    return int(b.decode("ascii", "replace").strip())


def read_edf_channels(
    path: str,
    *,
    want: Optional[list[str]] = None,
    target_fs: float = 2.0,
    max_duration_sec: Optional[float] = None,
) -> dict:
    """Return ``{fs, channels: {name: [float,...]}, duration_sec, labels}``.

    Downsamples each requested channel to ``target_fs`` by stride averaging.
    ``want`` is a list of lowercase substrings / exact names to keep
    (default: spo2, airflow/ptaf, one EEG, chest/abd).
    """
    if want is None:
        want = ["spo2", "ptaf", "airflow", "c4", "c3", "chest", "abd", "ecg"]

    with open(path, "rb") as f:
        header = f.read(256)
        ns = _int(header[252:256])
        ndr = _int(header[236:244])
        dur = float(header[244:252].decode("ascii", "replace").strip() or "1")
        labels = [f.read(16).decode("ascii", "replace").strip() for _ in range(ns)]
        for _ in range(ns):
            f.read(80)  # transducer
        for _ in range(ns):
            f.read(8)  # dim
        physmin = [float(f.read(8) or 0) for _ in range(ns)]
        physmax = [float(f.read(8) or 1) for _ in range(ns)]
        digmin = [float(f.read(8) or -32768) for _ in range(ns)]
        digmax = [float(f.read(8) or 32767) for _ in range(ns)]
        for _ in range(ns):
            f.read(80)
        nsamps = [_int(f.read(8)) for _ in range(ns)]
        for _ in range(ns):
            f.read(32)

        keep_idx: list[int] = []
        keep_names: list[str] = []
        seen: set[str] = set()
        for i, lab in enumerate(labels):
            if "Annot" in lab:
                continue
            low = lab.lower()
            for w in want:
                if w in low or low == w:
                    # Prefer canonical short names
                    name = low.replace(" ", "-")
                    if name in seen:
                        break
                    seen.add(name)
                    keep_idx.append(i)
                    keep_names.append(name)
                    break

        if max_duration_sec is not None:
            ndr = min(ndr, int(max_duration_sec / max(dur, 1e-6)))

        # Accumulate per-channel samples then downsample
        raw_bufs: dict[int, list[float]] = {i: [] for i in keep_idx}
        for _r in range(ndr):
            for i in range(ns):
                n = nsamps[i]
                blob = f.read(n * 2)
                if i not in raw_bufs:
                    continue
                if digmax[i] == digmin[i]:
                    continue
                scale = (physmax[i] - physmin[i]) / (digmax[i] - digmin[i])
                vals = struct.unpack("<" + "h" * n, blob)
                raw_bufs[i].extend(
                    (v - digmin[i]) * scale + physmin[i] for v in vals
                )

    duration_sec = ndr * dur
    channels: dict[str, list[float]] = {}
    for i, name in zip(keep_idx, keep_names):
        src_fs = nsamps[i] / dur if dur > 0 else float(nsamps[i])
        series = raw_bufs[i]
        if target_fs <= 0 or src_fs <= target_fs:
            channels[name] = [round(v, 3) for v in series]
            out_fs = src_fs
        else:
            stride = max(1, int(round(src_fs / target_fs)))
            down = []
            for k in range(0, len(series), stride):
                chunk = series[k : k + stride]
                down.append(round(sum(chunk) / len(chunk), 3))
            channels[name] = down
            out_fs = src_fs / stride

    return {
        "fs": round(out_fs, 4) if channels else target_fs,
        "channels": channels,
        "duration_sec": duration_sec,
        "labels": labels,
    }


def pick_spo2(channels: dict[str, list[float]]) -> Optional[list[float]]:
    for key, vals in channels.items():
        if "spo2" in key or "sao2" in key or key.endswith("o2"):
            return vals
    return None
