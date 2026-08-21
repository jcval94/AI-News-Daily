from __future__ import annotations

import unittest
from pathlib import Path

from pipeline.editorial_calibration import build_calibration_report


class EditorialCalibrationTests(unittest.TestCase):
    def test_real_baseline_exposes_judge_human_disagreement_without_premature_policy(self) -> None:
        report = build_calibration_report(Path("evals/editorial/cases.json"))
        self.assertEqual(report["case_count"], 3)
        self.assertEqual(report["human_publishable_count"], 0)
        self.assertEqual(report["human_reject_count"], 3)
        self.assertEqual(report["judge_metrics"]["seo"]["false_accept_count"], 3)
        self.assertEqual(report["judge_metrics"]["attention"]["false_accept_count"], 3)
        self.assertEqual(report["judge_metrics"]["voice"]["false_accept_count"], 0)
        self.assertFalse(report["calibration_readiness"]["ready_for_dimension_thresholds"])
        self.assertFalse(report["calibration_readiness"]["ready_for_judge_model_diversification_decision"])
        self.assertFalse(report["policy"]["voice_dimension_thresholds_active"])


if __name__ == "__main__":
    unittest.main()
