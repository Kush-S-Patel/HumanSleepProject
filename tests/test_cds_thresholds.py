"""Smoke tests for CDS thresholds and core imports (no S3 / Docker required)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "psg_core"))

from psg_core.cds import _osa_severity_adult, _osa_severity_pediatric, build_clinical_summary
from psg_core.clinical_refs import ADULT_OSA_AHI, PEDIATRIC_OSA_AHI
from psg_core.events import CAT_APNEA_OBSTRUCTIVE, ScoredEvent
from psg_core.hypnogram import Hypnogram
from psg_core.metrics import compute_metrics


class TestOsaThresholds(unittest.TestCase):
    def test_adult_boundaries(self):
        self.assertEqual(_osa_severity_adult(0)[0], "normal")
        self.assertEqual(_osa_severity_adult(4.9)[0], "normal")
        self.assertEqual(_osa_severity_adult(5)[0], "mild")
        self.assertEqual(_osa_severity_adult(14.9)[0], "mild")
        self.assertEqual(_osa_severity_adult(15)[0], "moderate")
        self.assertEqual(_osa_severity_adult(29.9)[0], "moderate")
        self.assertEqual(_osa_severity_adult(30)[0], "severe")

    def test_pediatric_boundaries(self):
        self.assertEqual(_osa_severity_pediatric(0.5)[0], "normal")
        self.assertEqual(_osa_severity_pediatric(1)[0], "mild")
        self.assertEqual(_osa_severity_pediatric(5)[0], "moderate")
        self.assertEqual(_osa_severity_pediatric(10)[0], "severe")

    def test_refs_present(self):
        self.assertTrue(ADULT_OSA_AHI["citations"])
        self.assertTrue(PEDIATRIC_OSA_AHI["citations"])


class TestMetricsSmoke(unittest.TestCase):
    def test_ahi_from_sleep_events(self):
        stages = ["W"] * 2 + ["N2"] * 120 + ["REM"] * 20 + ["W"] * 2
        hyp = Hypnogram(epoch_length_sec=30.0, stages=stages, source="test")
        # 10 obstructive events during sleep → AHI depends on TST hours
        events = [
            ScoredEvent(onset_sec=120 + i * 60, duration_sec=20, category=CAT_APNEA_OBSTRUCTIVE, subtype="OA")
            for i in range(10)
        ]
        m = compute_metrics(hyp, events)
        self.assertIsNotNone(m.get("ahi"))
        self.assertGreater(m["ahi"], 0)
        summary = build_clinical_summary(m, population="adult")
        self.assertIn(summary["osa_severity"], {"normal", "mild", "moderate", "severe", "unknown"})
        self.assertIn("Not a diagnosis", summary["disclaimer"])


if __name__ == "__main__":
    unittest.main()
