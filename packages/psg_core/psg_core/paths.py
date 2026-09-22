"""S3 / BIDS path helpers for the Human Sleep Project layout."""

from __future__ import annotations

import re

# Credentialed access-point alias for the BDSP repository bucket.
S3_ALIAS = "bdsp-credentialed-ac-psbrsg8wcmky4w5tbtn3b31yh4otause1b-s3alias"

# BIDS root inside the bucket.
BIDS_ROOT = "PSG/bids"


def sanitize(value: str) -> str:
    """Make a value safe for use in a filesystem path / URL segment."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(value))


def session_uid(site_id: str, patient_id: str, session_id: str) -> str:
    """Stable, human-readable identifier for a single PSG session.

    Patient-level identity is (site_id, patient_id); a patient may have many
    sessions, so the session id is appended.
    """
    return f"{sanitize(site_id)}-{sanitize(patient_id)}-{sanitize(session_id)}"


def patient_uid(site_id: str, patient_id: str) -> str:
    return f"{sanitize(site_id)}-{sanitize(patient_id)}"


def bids_eeg_prefix(cohort: str, bids_folder: str, session_id: str) -> str:
    """Return the BIDS ``.../eeg`` prefix (no trailing slash) for a session."""
    ses = f"ses-{sanitize(session_id)}"
    return f"{BIDS_ROOT}/{cohort}/{bids_folder}/{ses}/eeg"


def _file_stem(bids_folder: str, session_id: str) -> str:
    return f"{bids_folder}_ses-{sanitize(session_id)}"


def human_annotations_key(cohort: str, bids_folder: str, session_id: str) -> str:
    stem = _file_stem(bids_folder, session_id)
    return f"{bids_eeg_prefix(cohort, bids_folder, session_id)}/{stem}_task-psg_annotations.csv"


def channels_key(cohort: str, bids_folder: str, session_id: str) -> str:
    stem = _file_stem(bids_folder, session_id)
    return f"{bids_eeg_prefix(cohort, bids_folder, session_id)}/{stem}_task-psg_channels.tsv"


def eeg_json_key(cohort: str, bids_folder: str, session_id: str) -> str:
    stem = _file_stem(bids_folder, session_id)
    return f"{bids_eeg_prefix(cohort, bids_folder, session_id)}/{stem}_task-psg_eeg.json"


def edf_key(cohort: str, bids_folder: str, session_id: str) -> str:
    stem = _file_stem(bids_folder, session_id)
    return f"{bids_eeg_prefix(cohort, bids_folder, session_id)}/{stem}_task-psg_eeg.edf"


def h5_key(cohort: str, bids_folder: str, session_id: str) -> str:
    stem = _file_stem(bids_folder, session_id)
    return f"{bids_eeg_prefix(cohort, bids_folder, session_id)}/{stem}.h5"


def caisr_annotations_key(cohort: str, bids_folder: str, session_id: str) -> str:
    stem = _file_stem(bids_folder, session_id)
    return f"{bids_eeg_prefix(cohort, bids_folder, session_id)}/{stem}_caisr_annotations.csv"


def s3_uri(key: str, alias: str = S3_ALIAS) -> str:
    return f"s3://{alias}/{key}"
