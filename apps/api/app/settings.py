"""Runtime configuration and psg_core path bootstrap."""

from __future__ import annotations

import os
import sys

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # apps/api
REPO_ROOT = os.path.dirname(os.path.dirname(API_DIR))  # repo root
PSG_CORE_PATH = os.path.join(REPO_ROOT, "packages", "psg_core")

if PSG_CORE_PATH not in sys.path:
    sys.path.insert(0, PSG_CORE_PATH)


class Settings:
    data_root: str = os.environ.get("HSP_DATA_ROOT", os.path.join(REPO_ROOT, "data"))
    metadata_dir: str = os.environ.get("HSP_METADATA_DIR", os.path.join(REPO_ROOT, "metadata"))
    repo_root: str = REPO_ROOT
    # Comma-separated list of allowed CORS origins for the web app.
    cors_origins: list[str] = (
        os.environ.get("HSP_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    )
    # Whether the CAISR docker pipeline is available for real EDF/H5 scoring.
    enable_caisr: bool = os.environ.get("HSP_ENABLE_CAISR", "1") not in ("0", "false", "False")

    @property
    def registry_dir(self) -> str:
        return os.path.join(self.data_root, "registry")

    @property
    def uploads_dir(self) -> str:
        return os.path.join(self.data_root, "uploads")

    @property
    def jobs_dir(self) -> str:
        return os.path.join(self.data_root, "jobs")


settings = Settings()
