"""psg_core: shared PSG parsing, metrics, and clinical decision-support logic.

Kept dependency-light (standard library only) so it can be imported by both the
FastAPI service and the offline data-preparation scripts.
"""

from .cds import build_clinical_summary
from .events import (
    STAGE_ORDER,
    classify_event,
    parse_annotations_csv,
    stage_from_label,
)
from .hypnogram import Hypnogram, build_hypnogram
from .metrics import compute_metrics
from .paths import (
    S3_ALIAS,
    bids_eeg_prefix,
    human_annotations_key,
    s3_uri,
    session_uid,
)

__all__ = [
    "STAGE_ORDER",
    "classify_event",
    "parse_annotations_csv",
    "stage_from_label",
    "Hypnogram",
    "build_hypnogram",
    "compute_metrics",
    "build_clinical_summary",
    "S3_ALIAS",
    "bids_eeg_prefix",
    "human_annotations_key",
    "s3_uri",
    "session_uid",
]

__version__ = "0.1.0"
