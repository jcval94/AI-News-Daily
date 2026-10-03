from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pipeline.production_preflight import (
    classify_model_error,
    evaluate_source_quality,
    next_scheduled_date,
    run_preflight,
)


class ProductionPreflightTests(unittest.TestCase):
    def test_future_missing_days_are_pending_but_historical_gaps_still_fail(self) -> None:
        coverage = {
            "sufficient": False,
            "missing_dates": ["2026-10-04", "2026-10-05"],
            "expected_dates": [],
        }
        with tempfile.TemporaryDirectory() as tmp, patch(
            "pipeline.production_preflight.evaluate_source_coverage", return_value=coverage
        ), patch(
            "pipeline.production_preflight.evaluate_source_quality", return_value={"sufficient": True}
        ):
            kwargs = dict(target_date=date(2026, 10, 6), news_dir=Path(tmp), min_ratio=.75,
                          model="test", api_key="", probe_fn=lambda *_: {"available": True, "status": "ok"})
            report = run_preflight(as_of=date(2026, 10, 3), **kwargs)
            self.assertTrue(report["pending"])
            self.assertFalse(report["ready"])
            self.assertEqual(report["blockers"], ["source_coverage"])
            report = run_preflight(as_of=date(2026, 10, 6), **kwargs)
            self.assertFalse(report["pending"])
            self.assertFalse(report["ready"])
            kwargs["probe_fn"] = lambda *_: {"available": False, "status": "missing_secret"}
            report = run_preflight(as_of=date(2026, 10, 3), **kwargs)
            self.assertFalse(report["pending"])
            self.assertIn("model_probe:missing_secret", report["blockers"])

    def test_next_scheduled_date_targets_tuesday_and_friday(self) -> None:
        self.assertEqual(next_scheduled_date(date(2026, 9, 28)), date(2026, 9, 29))
        self.assertEqual(next_scheduled_date(date(2026, 10, 1)), date(2026, 10, 2))
        self.assertEqual(next_scheduled_date(date(2026, 9, 29)), date(2026, 9, 29))

    def test_source_quality_requires_enough_parseable_items(self) -> None:
        coverage = {"expected_dates": ["2026-09-26"]}
        good_items = [SimpleNamespace(url=f"https://example.com/{i}") for i in range(5)]
        with tempfile.TemporaryDirectory() as tmp, patch(
            "pipeline.production_preflight.load_news_for_date",
            return_value=(Path(tmp) / "2026-09-26.txt", good_items),
        ), patch(
            "pipeline.production_preflight.classify_url",
            return_value="article",
        ):
            result = evaluate_source_quality(coverage, Path(tmp))
        self.assertTrue(result["sufficient"])

    def test_source_quality_rejects_thin_digest(self) -> None:
        coverage = {"expected_dates": ["2026-09-26"]}
        thin_items = [SimpleNamespace(url=f"https://example.com/{i}") for i in range(4)]
        with tempfile.TemporaryDirectory() as tmp, patch(
            "pipeline.production_preflight.load_news_for_date",
            return_value=(Path(tmp) / "2026-09-26.txt", thin_items),
        ), patch(
            "pipeline.production_preflight.classify_url",
            return_value="article",
        ):
            result = evaluate_source_quality(coverage, Path(tmp))
        self.assertFalse(result["sufficient"])

    def test_permanent_quota_is_classified_explicitly(self) -> None:
        self.assertEqual(
            classify_model_error(RuntimeError("OpenAIException - You have no credits remaining.")),
            "permanent_quota",
        )

    def test_model_probe_failure_blocks_readiness(self) -> None:
        coverage = {
            "sufficient": True,
            "expected_dates": ["2026-09-26"],
            "available_day_count": 1,
            "expected_day_count": 1,
            "coverage_ratio": 1.0,
        }
        quality = {"sufficient": True, "days": []}
        with tempfile.TemporaryDirectory() as tmp, patch(
            "pipeline.production_preflight.evaluate_source_coverage",
            return_value=coverage,
        ), patch(
            "pipeline.production_preflight.evaluate_source_quality",
            return_value=quality,
        ):
            result = run_preflight(
                as_of=date(2026, 9, 28),
                target_date=date(2026, 9, 29),
                news_dir=Path(tmp),
                min_ratio=0.75,
                model="gpt-test",
                api_key="secret",
                probe_fn=lambda _model, _key: {
                    "available": False,
                    "status": "permanent_quota",
                },
            )
        self.assertFalse(result["ready"])
        self.assertIn("model_probe:permanent_quota", result["blockers"])


if __name__ == "__main__":
    unittest.main()
