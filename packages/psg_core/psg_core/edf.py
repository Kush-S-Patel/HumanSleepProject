"""EDF utilities: prepare an uploaded EDF for CAISR preprocessing.

Pure-stdlib EDF surgery (no deps). Fixes common upload failures:

1. **Malformed annotations channel** — drop ``EDF Annotations`` so MNE can load.
2. **Non-canonical labels** — rename variants (``Thoracic Effort``, ``Nasal Airflow``,
   ``EEG C4-M1``, …) to CAISR's vocabulary (``chest``, ``airflow``, ``c4-m1``, …).
3. **Missing required siblings** — CAISR aborts unless *both* ``abd`` and ``chest``
   exist, and at least one EOG (``e1-m2`` / ``e2-m1``). When only one belt or one
   EOG is present we clone it under the missing name so preprocess can run.
"""

from __future__ import annotations

# Canonical CAISR channel names keyed by lower-cased variant.
_LABEL_REMAP = {
    # respiratory effort belts
    "chest effort": "chest",
    "thorax effort": "chest",
    "thoracic effort": "chest",
    "thorax": "chest",
    "thoracic": "chest",
    "chest res": "chest",
    "thor res": "chest",
    "effort tho": "chest",
    "abd effort": "abd",
    "abdominal effort": "abd",
    "abdomen effort": "abd",
    "abdomen": "abd",
    "abdominal": "abd",
    "abd res": "abd",
    "effort abd": "abd",
    # airflow / pressure
    "nasal airflow": "airflow",
    "airflow thermal": "airflow",
    "thermal airflow": "airflow",
    "oral airflow": "airflow",
    "air flow": "airflow",
    "nasal pressure": "ptaf",
    "pressure airflow": "ptaf",
    # oximetry / ecg / chin
    "sao2": "spo2",
    "o2 sat": "spo2",
    "o2sat": "spo2",
    "osat": "spo2",
    "ekg": "ecg",
    "chin emg": "chin1-chin2",
    "chin": "chin1-chin2",
    "emg chin": "chin1-chin2",
    "emg.subm": "chin1-chin2",
    # EOG variants (single bipolar → treat as e1-m2; clone fills e2)
    "eog loc-roc": "e1-m2",
    "eog roc-loc": "e1-m2",
    "loc-roc": "e1-m2",
    "roc-loc": "e1-m2",
    "eog(l)": "e1-m2",
    "eog l": "e1-m2",
    "eog-l": "e1-m2",
    "eog1": "e1-m2",
    "loc": "e1-m2",
    "e1": "e1-m2",
    "eog(r)": "e2-m1",
    "eog r": "e2-m1",
    "eog-r": "e2-m1",
    "eog2": "e2-m1",
    "roc": "e2-m1",
    "e2": "e2-m1",
}


def _int(b: bytes) -> int:
    return int(b.decode("ascii", "replace").strip())


def _canon_label(raw_label: str) -> str:
    """Map a raw EDF channel label to CAISR's canonical name (best effort)."""
    l = raw_label.strip().lower()
    # Strip a leading "eeg " prefix ("eeg c3-m2" → "c3-m2").
    if l.startswith("eeg ") and l != "eeg":
        l = l[4:].strip()
    if l.startswith("eog ") and l not in _LABEL_REMAP:
        # "eog e1-m2" → try the remainder
        rest = l[4:].strip()
        if rest in _LABEL_REMAP or rest in ("e1-m2", "e2-m1"):
            l = rest
    return _LABEL_REMAP.get(l, l)


def _pad16(label: str) -> bytes:
    return f"{label:<16.16s}".encode("ascii", "replace")


def sanitize_edf(src: str, dst: str) -> dict:
    """Rewrite ``src`` to ``dst`` ready for CAISR.

    Drops annotation channels, normalises labels, and synthesises missing
    ``abd``/``chest``/EOG siblings by cloning.

    Returns a provenance dict describing every mutation applied.
    """
    with open(src, "rb") as f:
        raw = f.read()

    ns = _int(raw[252:256])
    ndr = _int(raw[236:244])

    # Per-signal header layout (EDF): each field repeated ns times.
    sizes = [16, 80, 8, 8, 8, 8, 8, 80, 8, 32]
    offsets: list[int] = []
    o = 256
    for s in sizes:
        offsets.append(o)
        o += s * ns

    labels = [
        raw[256 + 16 * i : 256 + 16 * i + 16].decode("ascii", "replace").strip()
        for i in range(ns)
    ]
    nsamp_off = offsets[8]
    nsamps = [_int(raw[nsamp_off + 8 * i : nsamp_off + 8 * i + 8]) for i in range(ns)]

    drop = {i for i, lab in enumerate(labels) if "EDF Annotations" in lab}
    steps: list[str] = []
    if drop:
        steps.append(f"dropped_annotations:{len(drop)}")

    # Build ordered list of (canonical_label, source_signal_index).
    channels: list[tuple[str, int]] = []
    seen: set[str] = set()
    relabeled: list[str] = []
    for i in range(ns):
        if i in drop:
            continue
        canon = _canon_label(labels[i])
        if canon != labels[i].strip().lower() and canon != labels[i].strip():
            relabeled.append(f"{labels[i]}->{canon}")
        if canon in seen:
            # Prefer the first occurrence; skip duplicates after remap.
            continue
        seen.add(canon)
        channels.append((canon, i))
    if relabeled:
        steps.append("relabeled:" + ",".join(relabeled[:12]))

    by_name = {name: src_i for name, src_i in channels}
    cloned: list[str] = []

    def _clone(name: str, donor: str) -> None:
        if name in by_name or donor not in by_name:
            return
        src_i = by_name[donor]
        channels.append((name, src_i))
        by_name[name] = src_i
        cloned.append(f"{name}<= {donor}")

    # Effort belts: CAISR requires BOTH abd and chest.
    if "chest" in by_name and "abd" not in by_name:
        _clone("abd", "chest")
    elif "abd" in by_name and "chest" not in by_name:
        _clone("chest", "abd")

    # EOG: need at least one of e1-m2 / e2-m1; prefer both.
    if "e1-m2" in by_name and "e2-m1" not in by_name:
        _clone("e2-m1", "e1-m2")
    elif "e2-m1" in by_name and "e1-m2" not in by_name:
        _clone("e1-m2", "e2-m1")

    if cloned:
        steps.append("cloned:" + ",".join(cloned))

    ns2 = len(channels)

    top = bytearray(raw[:256])
    top[184:192] = f"{(ns2 + 1) * 256:<8d}".encode("ascii")
    top[192:236] = b" " * 44  # clear EDF+/EDF+D → plain EDF
    top[252:256] = f"{ns2:<4d}".encode("ascii")

    # Rebuild per-signal headers, cloning donor metadata for synthesised chans.
    new_sections = bytearray()
    for sec_idx, size in enumerate(sizes):
        off = offsets[sec_idx]
        for name, src_i in channels:
            if sec_idx == 0:
                new_sections += _pad16(name)
            else:
                new_sections += raw[off + size * src_i : off + size * src_i + size]

    rec_size = sum(nsamps) * 2
    data_start = (ns + 1) * 256
    chunk_bytes = [n * 2 for n in nsamps]
    starts: list[int] = []
    acc = 0
    for cb in chunk_bytes:
        starts.append(acc)
        acc += cb

    out_records = bytearray()
    for r in range(ndr):
        base = data_start + r * rec_size
        for _name, src_i in channels:
            s = base + starts[src_i]
            out_records += raw[s : s + chunk_bytes[src_i]]

    with open(dst, "wb") as out:
        out.write(top)
        out.write(new_sections)
        out.write(out_records)

    return {
        "dropped_annotations": bool(drop),
        "relabeled": relabeled,
        "cloned_channels": cloned,
        "steps": steps,
        "n_channels_in": ns,
        "n_channels_out": ns2,
    }
