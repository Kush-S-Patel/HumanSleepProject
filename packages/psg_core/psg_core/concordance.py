"""Pure-Python agreement metrics for CAISR-vs-human concordance.

No numpy/sklearn dependency so this runs anywhere psg_core does. Implements
Cohen's kappa, a confusion matrix, ROC-AUC (rank-based) and PR-AUC (trapezoid),
and one-vs-rest macro averaging for multiclass staging.
"""

from __future__ import annotations

from typing import Optional, Sequence


def confusion_matrix(y_true: Sequence[str], y_pred: Sequence[str], labels: list[str]) -> list[list[int]]:
    idx = {l: i for i, l in enumerate(labels)}
    m = [[0 for _ in labels] for _ in labels]
    for t, p in zip(y_true, y_pred):
        if t in idx and p in idx:
            m[idx[t]][idx[p]] += 1
    return m


def accuracy(y_true: Sequence[str], y_pred: Sequence[str]) -> Optional[float]:
    n = 0
    correct = 0
    for t, p in zip(y_true, y_pred):
        n += 1
        if t == p:
            correct += 1
    return correct / n if n else None


def cohen_kappa(y_true: Sequence[str], y_pred: Sequence[str], labels: list[str]) -> Optional[float]:
    m = confusion_matrix(y_true, y_pred, labels)
    n = sum(sum(row) for row in m)
    if n == 0:
        return None
    po = sum(m[i][i] for i in range(len(labels))) / n
    row_tot = [sum(m[i]) for i in range(len(labels))]
    col_tot = [sum(m[i][j] for i in range(len(labels))) for j in range(len(labels))]
    pe = sum((row_tot[i] / n) * (col_tot[i] / n) for i in range(len(labels)))
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def roc_auc(scores: Sequence[float], labels: Sequence[int]) -> Optional[float]:
    """ROC-AUC via the Mann-Whitney U statistic (handles ties)."""
    pairs = [(s, y) for s, y in zip(scores, labels) if y in (0, 1)]
    n_pos = sum(1 for _, y in pairs if y == 1)
    n_neg = len(pairs) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    # Rank scores (average ranks for ties).
    order = sorted(range(len(pairs)), key=lambda i: pairs[i][0])
    ranks = [0.0] * len(pairs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and pairs[order[j + 1]][0] == pairs[order[i]][0]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # 1-based average rank
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    sum_pos = sum(ranks[i] for i in range(len(pairs)) if pairs[i][1] == 1)
    u = sum_pos - n_pos * (n_pos + 1) / 2.0
    return u / (n_pos * n_neg)


def pr_auc(scores: Sequence[float], labels: Sequence[int]) -> Optional[float]:
    """Average precision (area under precision-recall) via threshold sweep."""
    pairs = sorted(
        [(s, y) for s, y in zip(scores, labels) if y in (0, 1)],
        key=lambda x: x[0],
        reverse=True,
    )
    total_pos = sum(1 for _, y in pairs if y == 1)
    if total_pos == 0:
        return None
    tp = 0
    fp = 0
    prev_recall = 0.0
    area = 0.0
    i = 0
    n = len(pairs)
    while i < n:
        thr = pairs[i][0]
        while i < n and pairs[i][0] == thr:
            if pairs[i][1] == 1:
                tp += 1
            else:
                fp += 1
            i += 1
        recall = tp / total_pos
        precision = tp / (tp + fp) if (tp + fp) else 1.0
        area += precision * (recall - prev_recall)
        prev_recall = recall
    return area


def multiclass_ovr(
    prob_by_class: dict[str, Sequence[float]],
    y_true: Sequence[str],
    labels: list[str],
) -> dict:
    """One-vs-rest macro ROC-AUC / PR-AUC across staging classes."""
    per_class: dict[str, dict] = {}
    aurocs: list[float] = []
    auprcs: list[float] = []
    for lbl in labels:
        probs = prob_by_class.get(lbl)
        if probs is None:
            continue
        bin_labels = [1 if t == lbl else 0 for t in y_true]
        au = roc_auc(probs, bin_labels)
        ap = pr_auc(probs, bin_labels)
        per_class[lbl] = {"auroc": au, "auprc": ap, "prevalence": sum(bin_labels) / len(bin_labels) if bin_labels else None}
        if au is not None:
            aurocs.append(au)
        if ap is not None:
            auprcs.append(ap)
    return {
        "per_class": per_class,
        "macro_auroc": sum(aurocs) / len(aurocs) if aurocs else None,
        "macro_auprc": sum(auprcs) / len(auprcs) if auprcs else None,
    }


def bland_altman(a: Sequence[float], b: Sequence[float]) -> dict:
    """Agreement of two paired measurement series (e.g. AHI human vs CAISR)."""
    diffs = [x - y for x, y in zip(a, b)]
    n = len(diffs)
    if n == 0:
        return {"n": 0}
    bias = sum(diffs) / n
    var = sum((d - bias) ** 2 for d in diffs) / (n - 1) if n > 1 else 0.0
    sd = var**0.5
    mae = sum(abs(d) for d in diffs) / n
    # Pearson correlation
    ma = sum(a) / n
    mb = sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    r = cov / ((va * vb) ** 0.5) if va > 0 and vb > 0 else None
    return {
        "n": n,
        "bias": round(bias, 3),
        "sd": round(sd, 3),
        "loa_lower": round(bias - 1.96 * sd, 3),
        "loa_upper": round(bias + 1.96 * sd, 3),
        "mae": round(mae, 3),
        "pearson_r": round(r, 4) if r is not None else None,
    }
