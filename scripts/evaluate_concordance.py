"""CAISR vs. human concordance on held-out HSP studies.

           UNSEEN STUDY
                |
      +---------+---------+
      v                   v
  CAISR output        Human scoring
      |                   |
      +---------+---------+
                v
            compare
                |
      +---------+---------+
      v         v         v
     kappa    AUROC     AUPRC
      |
      v
   AHI agreement

For each held-out session (cohorts I0002/I0003/I0006 by default, excluding any
CAISR training set), this downloads the human annotations and the per-sample
CAISR annotation CSV, then computes:

* Sleep staging: overall accuracy, Cohen's kappa (5-class), confusion matrix,
  and one-vs-rest macro AUROC/AUPRC from CAISR stage probabilities.
* Arousal detection: per-second AUROC/AUPRC from caisr_prob_arousal.
* AHI agreement: Bland-Altman bias / limits-of-agreement + correlation.

Usage:
    python scripts/evaluate_concordance.py --n 4
    python scripts/evaluate_concordance.py --cohorts I0002 I0006 --n 6
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import subprocess
import tempfile

from _common import data_root, ensure_dir

from psg_core.annotations import parse_study
from psg_core.concordance import (
    accuracy,
    bland_altman,
    cohen_kappa,
    confusion_matrix,
    multiclass_ovr,
    pr_auc,
    roc_auc,
)
from psg_core.events import CAT_AROUSAL, ScoredEvent
from psg_core.hypnogram import build_hypnogram
from psg_core.metrics import compute_metrics
from psg_core.paths import S3_ALIAS, bids_eeg_prefix, s3_uri

# Reuse the annotation-file discovery/download from the cache builder.
from build_cache import download_annotations  # noqa: E402

STAGE_LABELS = ["W", "N1", "N2", "N3", "REM"]
# CAISR probability columns map to these stages (column order in the CSV).
PROB_COLS = {
    "N3": "caisr_prob_n3",
    "N2": "caisr_prob_n2",
    "N1": "caisr_prob_n1",
    "REM": "caisr_prob_r",
    "W": "caisr_prob_w",
}
# resp_caisr integer codes counted toward AHI (apneas + hypopnea; RERA excluded).
RESP_AHI_CODES = {1, 2, 3, 4}
RESP_MAP = {1: "Obstructive apnea", 2: "Central apnea", 3: "Mixed apnea", 4: "Hypopnea", 5: "RERA"}

_COMBINED_CAISR_RE = re.compile(r"_caisr_annotations\.csv$", re.IGNORECASE)
_TASK_CAISR_RE = re.compile(r"_(arousal|resp|limb|stage|plm)_caisr_annotations\.csv$", re.IGNORECASE)


def load_sessions(root: str) -> list[dict]:
    path = os.path.join(root, "registry", "sessions.json")
    if not os.path.exists(path):
        raise SystemExit("registry not found; run scripts/build_registry.py first")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def select_heldout(sessions: list[dict], cohorts: list[str], n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    pool = [
        s
        for s in sessions
        if s.get("cohort") in cohorts
        and s.get("has_sleep_annotations")
        and not s.get("caisr_training_set")  # exclude CAISR training set when known
        and not s.get("synthetic")
    ]
    # One session per patient.
    by_patient: dict[str, dict] = {}
    for s in pool:
        by_patient.setdefault(s["patient_uid"], s)
    unique = list(by_patient.values())
    rng.shuffle(unique)
    return unique


def find_caisr_key(session: dict) -> str | None:
    prefix = bids_eeg_prefix(session["cohort"], session["bids_folder"], session["session_id"])
    uri = s3_uri(prefix + "/", S3_ALIAS)
    try:
        res = subprocess.run(["aws", "s3", "ls", uri], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError:
        return None
    for line in res.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        name = parts[-1]
        if _COMBINED_CAISR_RE.search(name) and not _TASK_CAISR_RE.search(name):
            return f"{prefix}/{name}"
    return None


def stream_caisr(path: str, fs: int, epoch_sec: int):
    """Stream a per-sample CAISR CSV, aggregating without holding all rows.

    Returns dict with caisr_stage_epochs, epoch_probs (per class), arousal
    per-second probabilities, and CAISR respiratory events.
    """
    samples_per_epoch = fs * epoch_sec
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        col = {name: i for i, name in enumerate(header)}
        prob_idx = {stg: col.get(cname) for stg, cname in PROB_COLS.items()}
        arousal_prob_idx = col.get("caisr_prob_arousal")
        resp_idx = col.get("resp_caisr")

        stage_epochs: list[str] = []
        epoch_probs: dict[str, list[float]] = {s: [] for s in STAGE_LABELS}
        arousal_sec: list[float] = []

        # per-epoch accumulators
        cur_epoch = 0
        prob_sum = {s: 0.0 for s in STAGE_LABELS}
        valid_count = 0
        # per-second accumulator
        cur_sec = 0
        sec_max = 0.0
        # resp run-length
        resp_events: list[ScoredEvent] = []
        resp_cur = 0
        resp_start = 0

        i = 0
        for row in reader:
            # --- staging probabilities (skip invalid 9.0 placeholders) ---
            valid = True
            vals = {}
            for stg, idx in prob_idx.items():
                if idx is None:
                    valid = False
                    break
                try:
                    v = float(row[idx])
                except (ValueError, IndexError):
                    valid = False
                    break
                if v > 1.0:  # 9.0 placeholder = no prediction
                    valid = False
                    break
                vals[stg] = v
            if valid:
                for stg in STAGE_LABELS:
                    prob_sum[stg] += vals[stg]
                valid_count += 1

            # --- arousal per-second max prob ---
            if arousal_prob_idx is not None:
                try:
                    ap = float(row[arousal_prob_idx])
                    if ap <= 1.0:
                        sec_max = max(sec_max, ap)
                except (ValueError, IndexError):
                    pass

            # --- respiratory run-length ---
            if resp_idx is not None:
                try:
                    rc = int(float(row[resp_idx]))
                except (ValueError, IndexError):
                    rc = 0
                if rc != resp_cur:
                    if resp_cur in RESP_MAP:
                        onset = resp_start / fs
                        dur = (i - resp_start) / fs
                        resp_events.append(ScoredEvent(onset, dur, "resp", RESP_MAP[resp_cur]))
                    resp_cur = rc
                    resp_start = i

            i += 1

            # roll second
            if i // fs != cur_sec:
                arousal_sec.append(sec_max)
                sec_max = 0.0
                cur_sec = i // fs

            # roll epoch
            if i // samples_per_epoch != cur_epoch:
                if valid_count > 0:
                    means = {s: prob_sum[s] / valid_count for s in STAGE_LABELS}
                    stage_epochs.append(max(STAGE_LABELS, key=lambda s: means[s]))
                    for s in STAGE_LABELS:
                        epoch_probs[s].append(means[s])
                else:
                    stage_epochs.append("?")
                    for s in STAGE_LABELS:
                        epoch_probs[s].append(0.0)
                prob_sum = {s: 0.0 for s in STAGE_LABELS}
                valid_count = 0
                cur_epoch = i // samples_per_epoch

        # flush trailing resp event
        if resp_cur in RESP_MAP:
            resp_events.append(ScoredEvent(resp_start / fs, (i - resp_start) / fs, "resp", RESP_MAP[resp_cur]))

    return {
        "stage_epochs": stage_epochs,
        "epoch_probs": epoch_probs,
        "arousal_sec": arousal_sec,
        "resp_events": resp_events,
        "n_samples": i,
    }


def human_arousal_per_second(events: list[ScoredEvent], total_sec: int) -> list[int]:
    arr = [0] * total_sec
    for e in events:
        if e.category != CAT_AROUSAL:
            continue
        a = max(0, int(e.onset_sec))
        b = min(total_sec, int(e.onset_sec + max(1.0, e.duration_sec)) + 1)
        for t in range(a, b):
            arr[t] = 1
    return arr


def caisr_ahi(stream: dict, epoch_sec: int) -> float | None:
    hyp = build_hypnogram(stream["stage_epochs"], float(epoch_sec), None, "caisr")
    apnea_hypopnea = [e for e in stream["resp_events"] if e.subtype in ("Obstructive apnea", "Central apnea", "Mixed apnea", "Hypopnea")]
    # Reuse metric engine by mapping resp subtypes to the standard categories.
    from psg_core.events import (
        CAT_APNEA_CENTRAL,
        CAT_APNEA_MIXED,
        CAT_APNEA_OBSTRUCTIVE,
        CAT_HYPOPNEA,
    )

    cat_map = {
        "Obstructive apnea": CAT_APNEA_OBSTRUCTIVE,
        "Central apnea": CAT_APNEA_CENTRAL,
        "Mixed apnea": CAT_APNEA_MIXED,
        "Hypopnea": CAT_HYPOPNEA,
    }
    mapped = [ScoredEvent(e.onset_sec, e.duration_sec, cat_map[e.subtype], e.subtype) for e in apnea_hypopnea]
    m = compute_metrics(hyp, mapped)
    return m.get("ahi")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default=data_root())
    ap.add_argument("--cohorts", nargs="*", default=["I0002", "I0003", "I0006"])
    ap.add_argument("--n", type=int, default=12, help="held-out sessions to evaluate (cohort-scale)")
    ap.add_argument("--fs", type=int, default=200, help="CAISR annotation sample rate (Hz)")
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()

    sessions = load_sessions(args.data_root)
    candidates = select_heldout(sessions, args.cohorts, args.n, args.seed)

    # Pools across sessions.
    y_true_stage: list[str] = []
    y_pred_stage: list[str] = []
    stage_prob_pool: dict[str, list[float]] = {s: [] for s in STAGE_LABELS}
    arousal_scores: list[float] = []
    arousal_labels: list[int] = []
    human_ahis: list[float] = []
    caisr_ahis: list[float] = []
    per_session: list[dict] = []

    used = 0
    with tempfile.TemporaryDirectory() as tmp:
        for s in candidates:
            if used >= args.n:
                break
            caisr_key = find_caisr_key(s)
            if not caisr_key:
                continue
            ann = download_annotations(s, tmp)
            if not ann:
                continue

            print(f"[eval] {s['uid']} ({s['cohort']}) — downloading CAISR annotations…", flush=True)
            caisr_local = os.path.join(tmp, f"{s['uid']}_caisr.csv")
            try:
                subprocess.run(
                    ["aws", "s3", "cp", s3_uri(caisr_key, S3_ALIAS), caisr_local, "--no-progress"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as exc:
                print(f"  ! CAISR download failed: {exc.stderr.strip()[:160]}")
                continue

            human = parse_study(combined=ann.get("combined"), sleep=ann.get("sleep"), events=ann.get("events"))
            if not human.stage_epochs:
                print("  ! no human staging; skipping")
                os.remove(caisr_local)
                continue

            print("  parsing CAISR (streaming)…", flush=True)
            stream = stream_caisr(caisr_local, args.fs, 30)
            os.remove(caisr_local)

            # --- staging pooling ---
            n_ep = min(len(human.stage_epochs), len(stream["stage_epochs"]))
            sess_true, sess_pred = [], []
            for i in range(n_ep):
                ht = human.stage_epochs[i]
                ct = stream["stage_epochs"][i]
                if ht in STAGE_LABELS and ct in STAGE_LABELS:
                    y_true_stage.append(ht)
                    y_pred_stage.append(ct)
                    sess_true.append(ht)
                    sess_pred.append(ct)
                    for stg in STAGE_LABELS:
                        stage_prob_pool[stg].append(stream["epoch_probs"][stg][i])

            # --- arousal pooling (per second) ---
            total_sec = n_ep * 30
            h_ar = human_arousal_per_second(human.events, total_sec)
            c_ar = stream["arousal_sec"]
            m = min(len(h_ar), len(c_ar))
            arousal_labels.extend(h_ar[:m])
            arousal_scores.extend(c_ar[:m])

            # --- AHI agreement ---
            h_metrics = compute_metrics(
                build_hypnogram(human.stage_epochs, 30.0, None, "human"), human.events
            )
            h_ahi = h_metrics.get("ahi")
            c_ahi = caisr_ahi(stream, 30)
            if h_ahi is not None and c_ahi is not None:
                human_ahis.append(h_ahi)
                caisr_ahis.append(c_ahi)

            sess_kappa = cohen_kappa(sess_true, sess_pred, STAGE_LABELS)
            per_session.append(
                {
                    "uid": s["uid"],
                    "cohort": s["cohort"],
                    "n_epochs": n_ep,
                    "staging_accuracy": accuracy(sess_true, sess_pred),
                    "staging_kappa": sess_kappa,
                    "human_ahi": h_ahi,
                    "caisr_ahi": c_ahi,
                }
            )
            print(
                f"  ok — epochs={n_ep} acc={accuracy(sess_true, sess_pred):.3f} "
                f"kappa={sess_kappa:.3f} humanAHI={h_ahi} caisrAHI={c_ahi}",
                flush=True,
            )
            used += 1

    if used == 0:
        raise SystemExit("no eligible sessions with both human + CAISR annotations were found")

    # --- aggregate metrics ---
    staging = {
        "n_epochs": len(y_true_stage),
        "accuracy": accuracy(y_true_stage, y_pred_stage),
        "cohen_kappa": cohen_kappa(y_true_stage, y_pred_stage, STAGE_LABELS),
        "labels": STAGE_LABELS,
        "confusion_matrix": confusion_matrix(y_true_stage, y_pred_stage, STAGE_LABELS),
        **multiclass_ovr(stage_prob_pool, y_true_stage, STAGE_LABELS),
    }
    arousal = {
        "n_seconds": len(arousal_labels),
        "positive_rate": (sum(arousal_labels) / len(arousal_labels)) if arousal_labels else None,
        "auroc": roc_auc(arousal_scores, arousal_labels),
        "auprc": pr_auc(arousal_scores, arousal_labels),
    }
    ahi = bland_altman(human_ahis, caisr_ahis)
    ahi["points"] = [
        {
            "uid": s["uid"],
            "cohort": s.get("cohort"),
            "human": s["human_ahi"],
            "caisr": s["caisr_ahi"],
            "mean": round((s["human_ahi"] + s["caisr_ahi"]) / 2.0, 3),
            "diff": round(s["human_ahi"] - s["caisr_ahi"], 3),
        }
        for s in per_session
        if s.get("human_ahi") is not None and s.get("caisr_ahi") is not None
    ]
    by_cohort: dict[str, dict] = {}
    for s in per_session:
        c = s.get("cohort") or "?"
        b = by_cohort.setdefault(c, {"n": 0, "kappas": [], "accuracies": []})
        b["n"] += 1
        if s.get("staging_kappa") is not None:
            b["kappas"].append(s["staging_kappa"])
        if s.get("staging_accuracy") is not None:
            b["accuracies"].append(s["staging_accuracy"])
    by_cohort_summary = {
        c: {
            "n": v["n"],
            "mean_kappa": round(sum(v["kappas"]) / len(v["kappas"]), 4) if v["kappas"] else None,
            "mean_accuracy": round(sum(v["accuracies"]) / len(v["accuracies"]), 4)
            if v["accuracies"]
            else None,
        }
        for c, v in sorted(by_cohort.items())
    }

    report = {
        "n_sessions": used,
        "cohorts": args.cohorts,
        "staging": staging,
        "arousal": arousal,
        "ahi_agreement": ahi,
        "by_cohort": by_cohort_summary,
        "per_session": per_session,
    }

    out_dir = ensure_dir(os.path.join(args.data_root, "eval"))
    out_path = os.path.join(out_dir, "concordance.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    _print_report(report)
    print(f"\n[eval] wrote {out_path}")


def _fmt(v, d=3):
    return "n/a" if v is None else f"{v:.{d}f}"


def _print_report(r: dict) -> None:
    s = r["staging"]
    a = r["arousal"]
    h = r["ahi_agreement"]
    print("\n" + "=" * 60)
    print(f"CAISR vs HUMAN concordance  ({r['n_sessions']} held-out sessions)")
    print("=" * 60)
    print("\nSLEEP STAGING")
    print(f"  epochs           {s['n_epochs']}")
    print(f"  accuracy         {_fmt(s['accuracy'])}")
    print(f"  Cohen's kappa    {_fmt(s['cohen_kappa'])}")
    print(f"  macro AUROC      {_fmt(s['macro_auroc'])}")
    print(f"  macro AUPRC      {_fmt(s['macro_auprc'])}")
    print("  per-stage AUROC / AUPRC:")
    for lbl in s["labels"]:
        pc = s["per_class"].get(lbl, {})
        print(f"    {lbl:4s}  AUROC {_fmt(pc.get('auroc'))}  AUPRC {_fmt(pc.get('auprc'))}  prev {_fmt(pc.get('prevalence'))}")
    print("  confusion (rows=human, cols=CAISR): " + " ".join(s["labels"]))
    for i, lbl in enumerate(s["labels"]):
        print(f"    {lbl:4s} " + " ".join(f"{v:6d}" for v in s["confusion_matrix"][i]))
    print("\nAROUSAL DETECTION (per second)")
    print(f"  seconds          {a['n_seconds']}")
    print(f"  positive rate    {_fmt(a['positive_rate'])}")
    print(f"  AUROC            {_fmt(a['auroc'])}")
    print(f"  AUPRC            {_fmt(a['auprc'])}")
    print("\nAHI AGREEMENT (human vs CAISR)")
    print(f"  n sessions       {h.get('n')}")
    print(f"  bias             {h.get('bias')}")
    print(f"  95% LoA          [{h.get('loa_lower')}, {h.get('loa_upper')}]")
    print(f"  MAE              {h.get('mae')}")
    print(f"  Pearson r        {h.get('pearson_r')}")


if __name__ == "__main__":
    main()
