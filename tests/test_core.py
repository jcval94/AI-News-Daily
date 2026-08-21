from __future__ import annotations

import unittest
from datetime import date

from pipeline.core import (
    PipelineConfig,
    build_timeline_slots,
    duration_within_target,
    evaluate_script_gate,
    expected_news_dates,
    is_retryable_exception,
    timeline_duration_seconds,
)


class DummyRateLimitError(Exception):
    status_code = 429


class CoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = PipelineConfig().validated()

    def test_tuesday_window(self) -> None:
        self.assertEqual(
            [d.isoformat() for d in expected_news_dates(date(2026, 8, 25))],
            ["2026-08-21", "2026-08-22", "2026-08-23", "2026-08-24"],
        )

    def test_friday_window(self) -> None:
        self.assertEqual(
            [d.isoformat() for d in expected_news_dates(date(2026, 8, 21))],
            ["2026-08-18", "2026-08-19", "2026-08-20"],
        )

    def test_duration_bounds(self) -> None:
        self.assertTrue(duration_within_target("x " * 1050, self.config))
        self.assertTrue(duration_within_target("x " * 1800, self.config))
        self.assertFalse(duration_within_target("x " * 1000, self.config))
        self.assertFalse(duration_within_target("x " * 1900, self.config))

    def test_timeline_never_truncates_narration(self) -> None:
        script = "x " * 1800
        duration = timeline_duration_seconds(script, self.config)
        self.assertGreaterEqual(duration, self.config.target_max_seconds)
        slots = build_timeline_slots(duration, self.config)
        self.assertEqual([(s["start_seconds"], s["end_seconds"]) for s in slots[:5]], [(0, 3), (3, 6), (6, 9), (9, 12), (12, 15)])
        self.assertEqual((slots[5]["start_seconds"], slots[5]["end_seconds"]), (15, 19))
        self.assertEqual(slots[-1]["end_seconds"], duration)

    def test_gate_is_deterministic(self) -> None:
        script = "x " * 1050
        editorial = {"approved": True, "score": 9.0, "factuality_risk": "low"}
        seo = {"approved": True, "score": 9.0}
        attention = {"approved": True, "score": 9.0}
        self.assertTrue(evaluate_script_gate(script, editorial, seo, attention, self.config)["approved"])
        editorial["factuality_risk"] = "medium"
        self.assertFalse(evaluate_script_gate(script, editorial, seo, attention, self.config)["approved"])

    def test_retry_classification(self) -> None:
        self.assertTrue(is_retryable_exception(DummyRateLimitError("rate")))
        self.assertFalse(is_retryable_exception(ValueError("bad input")))


if __name__ == "__main__":
    unittest.main()
