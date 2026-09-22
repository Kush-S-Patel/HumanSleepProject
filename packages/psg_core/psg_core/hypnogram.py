"""Hypnogram representation and helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .events import STAGE_ORDER, STAGE_UNKNOWN

SLEEP_STAGES = {"N1", "N2", "N3", "REM"}


@dataclass
class Hypnogram:
    epoch_length_sec: float
    stages: list[str]  # canonical: W/N1/N2/N3/REM/?
    start_clock: Optional[str] = None
    source: str = "human"

    @property
    def n_epochs(self) -> int:
        return len(self.stages)

    def scored_bounds(self) -> tuple[Optional[int], Optional[int]]:
        """First/last epoch index (0-based) that is not unknown."""
        first = next((i for i, s in enumerate(self.stages) if s != STAGE_UNKNOWN), None)
        last = None
        for i in range(len(self.stages) - 1, -1, -1):
            if self.stages[i] != STAGE_UNKNOWN:
                last = i
                break
        return first, last

    def sleep_bounds(self) -> tuple[Optional[int], Optional[int]]:
        """First/last epoch index (0-based) scored as any sleep stage."""
        first = next((i for i, s in enumerate(self.stages) if s in SLEEP_STAGES), None)
        last = None
        for i in range(len(self.stages) - 1, -1, -1):
            if self.stages[i] in SLEEP_STAGES:
                last = i
                break
        return first, last


def build_hypnogram(
    stage_epochs: list[str],
    epoch_length_sec: float = 30.0,
    start_clock: Optional[str] = None,
    source: str = "human",
) -> Hypnogram:
    return Hypnogram(
        epoch_length_sec=epoch_length_sec,
        stages=list(stage_epochs),
        start_clock=start_clock,
        source=source,
    )


def stage_counts(hyp: Hypnogram) -> dict[str, int]:
    counts = {s: 0 for s in STAGE_ORDER}
    counts[STAGE_UNKNOWN] = 0
    for s in hyp.stages:
        counts[s] = counts.get(s, 0) + 1
    return counts
