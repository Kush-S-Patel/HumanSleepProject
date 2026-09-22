"""Shared path/bootstrap helpers for the data-preparation scripts."""

from __future__ import annotations

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PSG_CORE_PATH = os.path.join(REPO_ROOT, "packages", "psg_core")
DEFAULT_DATA_ROOT = os.path.join(REPO_ROOT, "data")
DEFAULT_METADATA_DIR = os.path.join(REPO_ROOT, "metadata")

if PSG_CORE_PATH not in sys.path:
    sys.path.insert(0, PSG_CORE_PATH)


def data_root() -> str:
    return os.environ.get("HSP_DATA_ROOT", DEFAULT_DATA_ROOT)


def metadata_dir() -> str:
    return os.environ.get("HSP_METADATA_DIR", DEFAULT_METADATA_DIR)


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path
