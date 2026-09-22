"""Clinical decision-support narrative generation.

Turns computed metrics + study context into severity classifications and
plain-language findings. This is decision *support* only: every payload carries
an explicit disclaimer and is not a diagnosis.

OSA severity cut-points follow common AASM / clinical-practice ranges.
Citations live in ``psg_core.clinical_refs`` and ``docs/CLINICAL_REFERENCES.md``.
"""

from __future__ import annotations

from typing import Optional

from . import clinical_refs as refs

DISCLAIMER = (
    "Automated decision support for review by a qualified sleep clinician. "
    "Not a diagnosis. AI-generated scoring must be verified against the raw "
    "polysomnogram before any clinical action."
)


def _osa_severity_adult(ahi: Optional[float]) -> tuple[str, str]:
    """Adult OSA severity by AHI (events/h sleep). See ``clinical_refs.ADULT_OSA_AHI``."""
    _ = refs.ADULT_OSA_AHI  # keep module linked for importers / docs
    if ahi is None:
        return "unknown", "AHI could not be computed"
    if ahi < 5:
        return "normal", "AHI < 5 (adult; AASM/clinical practice)"
    if ahi < 15:
        return "mild", "5 <= AHI < 15 (adult; AASM/clinical practice)"
    if ahi < 30:
        return "moderate", "15 <= AHI < 30 (adult; AASM/clinical practice)"
    return "severe", "AHI >= 30 (adult; AASM/clinical practice)"


def _osa_severity_pediatric(ahi: Optional[float]) -> tuple[str, str]:
    """Pediatric OSA severity — more sensitive cut-points. See ``clinical_refs.PEDIATRIC_OSA_AHI``."""
    _ = refs.PEDIATRIC_OSA_AHI
    if ahi is None:
        return "unknown", "AHI could not be computed"
    if ahi < 1:
        return "normal", "AHI < 1 (pediatric; AASM/ICSD)"
    if ahi < 5:
        return "mild", "1 <= AHI < 5 (pediatric)"
    if ahi < 10:
        return "moderate", "5 <= AHI < 10 (pediatric)"
    return "severe", "AHI >= 10 (pediatric)"


def _severity_rank(name: str) -> int:
    return {"normal": 0, "unknown": 0, "mild": 1, "moderate": 2, "severe": 3}.get(name, 0)


def build_clinical_summary(
    metrics: dict,
    *,
    population: str = "adult",
    age: Optional[float] = None,
    study_type: Optional[str] = None,
    has_staging: bool = True,
    has_events: bool = True,
) -> dict:
    """Return a structured clinical-decision-support summary.

    ``population`` is "pediatric" or "adult" (drives OSA thresholds).
    """
    is_pediatric = (population or "").lower().startswith("ped") or (age is not None and age < 18)

    ahi = metrics.get("ahi")
    if is_pediatric:
        osa_sev, osa_basis = _osa_severity_pediatric(ahi)
    else:
        osa_sev, osa_basis = _osa_severity_adult(ahi)

    # Insufficient scored sleep → do not claim OSA severity from a missing AHI.
    tst = metrics.get("total_sleep_time_min")
    index_valid = metrics.get("index_valid", True)
    if not index_valid or (tst is not None and tst < 5):
        osa_sev, osa_basis = "unknown", "insufficient scored sleep for reliable AHI"

    findings: list[dict] = []

    # --- Respiratory ---
    n_ob = metrics.get("n_obstructive_apnea", 0) or 0
    n_ce = metrics.get("n_central_apnea", 0) or 0
    n_mx = metrics.get("n_mixed_apnea", 0) or 0
    n_hy = metrics.get("n_hypopnea", 0) or 0
    total_resp = n_ob + n_ce + n_mx + n_hy

    if not index_valid or (tst is not None and tst < 5):
        findings.append(
            {
                "domain": "quality",
                "severity": "moderate",
                "title": "Insufficient scored sleep",
                "detail": (
                    f"Total sleep time {tst} min — too little scored sleep for a reliable AHI. "
                    "Staging may reflect wake/artifact (common on synthetic or very noisy recordings). "
                    f"CAISR still marked {total_resp} respiratory events across the recording "
                    f"({metrics.get('n_apnea_hypopnea_in_sleep', 0)} during sleep epochs)."
                ),
            }
        )
    elif ahi is not None:
        predominance = "obstructive"
        if total_resp > 0 and n_ce >= 0.5 * (n_ob + n_ce + n_mx + 1e-9) and n_ce > n_ob:
            predominance = "central"
        if osa_sev in ("mild", "moderate", "severe"):
            label = "Central sleep apnea" if predominance == "central" else "Obstructive sleep apnea"
            findings.append(
                {
                    "domain": "respiratory",
                    "severity": osa_sev,
                    "title": f"{osa_sev.capitalize()} {label.lower()}",
                    "detail": (
                        f"AHI {ahi} events/h ({osa_basis}); "
                        f"predominantly {predominance} events "
                        f"({n_ob} obstructive, {n_ce} central, {n_mx} mixed, {n_hy} hypopnea)."
                    ),
                }
            )
        else:
            findings.append(
                {
                    "domain": "respiratory",
                    "severity": "normal",
                    "title": "No significant sleep-disordered breathing",
                    "detail": f"AHI {ahi} events/h ({osa_basis}).",
                }
            )

    spo2_nadir = metrics.get("spo2_nadir")
    if spo2_nadir is not None and spo2_nadir < 90 and index_valid:
        sev = "severe" if spo2_nadir < 80 else ("moderate" if spo2_nadir < 85 else "mild")
        findings.append(
            {
                "domain": "oxygenation",
                "severity": sev,
                "title": "Nocturnal oxygen desaturation",
                "detail": f"SpO2 nadir {spo2_nadir}% with ODI {metrics.get('odi')} events/h.",
            }
        )

    # --- Sleep architecture ---
    if index_valid:
        eff = metrics.get("sleep_efficiency_pct")
        if eff is not None and eff < 85:
            sev = "moderate" if eff < 75 else "mild"
            findings.append(
                {
                    "domain": "architecture",
                    "severity": sev,
                    "title": "Reduced sleep efficiency",
                    "detail": (
                        f"Sleep efficiency {eff}% with WASO {metrics.get('waso_min')} min "
                        f"and sleep latency {metrics.get('sleep_latency_min')} min."
                    ),
                }
            )

        n3_pct = metrics.get("n3_pct")
        if n3_pct is not None and not is_pediatric and n3_pct < 10:
            findings.append(
                {
                    "domain": "architecture",
                    "severity": "mild",
                    "title": "Reduced slow-wave sleep",
                    "detail": f"N3 {n3_pct}% of TST (expected >= 10-15% in adults).",
                }
            )

        rem_pct = metrics.get("rem_pct")
        if rem_pct is not None and rem_pct < 15:
            findings.append(
                {
                    "domain": "architecture",
                    "severity": "mild",
                    "title": "Reduced REM sleep",
                    "detail": f"REM {rem_pct}% of TST (expected ~20-25%); consider REM suppression.",
                }
            )

    # --- Arousals / fragmentation ---
    ar = metrics.get("arousal_index")
    if index_valid and ar is not None and ar >= 15:
        sev = "moderate" if ar >= 25 else "mild"
        findings.append(
            {
                "domain": "arousals",
                "severity": sev,
                "title": "Elevated arousal index",
                "detail": f"Arousal index {ar}/h; sleep fragmentation index {metrics.get('sleep_fragmentation_index')}/h.",
            }
        )

    # --- Limb movements ---
    plmi = metrics.get("plm_index")
    if index_valid and plmi is not None and plmi >= 15:
        findings.append(
            {
                "domain": "limb",
                "severity": "mild",
                "title": "Periodic limb movements",
                "detail": f"PLM index {plmi}/h; correlate with clinical symptoms of RLS/PLMD.",
            }
        )

    # --- Caveats that materially change interpretation ---
    caveats: list[str] = []
    st = (study_type or "").lower()
    if any(k in st for k in ("cpap", "titration", "bilevel", "pap", "bipap")):
        caveats.append(
            "PAP was administered during this study; respiratory indices reflect treated sleep and understate untreated severity."
        )
    if "split" in st:
        caveats.append(
            "Split-night study: diagnostic and titration segments are combined; interpret whole-night indices with caution."
        )
    if not has_events:
        caveats.append("No event annotations available; respiratory and arousal indices are unavailable.")
    if not has_staging:
        caveats.append("No sleep staging available; architecture metrics and per-hour indices are unavailable.")
    if not index_valid or (tst is not None and tst < 5):
        caveats.append(
            "Insufficient scored sleep (< 5 min): AHI/RDI and other per-hour indices are withheld. "
            "Review the hypnogram — all-wake scoring often means the recording is noise, "
            "truncated, or missing usable EEG for staging."
        )
    if is_pediatric:
        caveats.append("Pediatric AASM thresholds applied (AHI >= 1 abnormal).")

    overall = max((f["severity"] for f in findings), key=_severity_rank, default="normal")

    return {
        "population": "pediatric" if is_pediatric else "adult",
        "osa_severity": osa_sev,
        "overall_severity": overall,
        "headline": _headline(osa_sev, overall, is_pediatric, index_valid=bool(index_valid)),
        "findings": findings,
        "caveats": caveats,
        "disclaimer": DISCLAIMER,
    }


def _headline(osa_sev: str, overall: str, is_pediatric: bool, index_valid: bool = True) -> str:
    who = "Pediatric study" if is_pediatric else "Adult study"
    if not index_valid or osa_sev == "unknown":
        return f"{who}: insufficient scored sleep - review staging before interpreting AHI"
    if osa_sev in ("mild", "moderate", "severe"):
        return f"{who}: {osa_sev} sleep apnea identified"
    if overall in ("mild", "moderate", "severe"):
        return f"{who}: no significant apnea; other findings need review"
    return f"{who}: within normal limits on automated review"
