from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.source_coverage import evaluate_source_coverage


NEWS_TEMPLATE = """## 1. Example AI development
Fecha: {date}
Fuente: Example Source
Enlace: https://example.com/{date}
Categoría: AI
Resumen: Example structured news item.
Por qué importa: It is useful for testing source coverage.
"""


class SourceCoverageTests(unittest.TestCase):
    def _write_day(self, root: Path, value: str) -> None:
        (root / f"{value}.txt").write_text(NEWS_TEMPLATE.format(date=value), encoding="utf-8")

    def test_three_of_four_days_passes_default_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"NEWS_SOURCE_MODE": "recent_window", "NEWS_LOOKBACK_DAYS": "4"},
            clear=False,
        ):
            root = Path(tmp)
            for value in ("2026-08-22", "2026-08-23", "2026-08-24"):
                self._write_day(root, value)
            result = evaluate_source_coverage(
                target_date="2026-08-24",
                news_dir=root,
                min_ratio=0.75,
            )
            self.assertTrue(result["sufficient"])
            self.assertEqual(result["available_day_count"], 3)
            self.assertEqual(result["expected_day_count"], 4)
            self.assertEqual(result["coverage_ratio"], 0.75)

    def test_friday_scheduled_window_accepts_timestamped_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"NEWS_SOURCE_MODE": "scheduled_window", "NEWS_LOOKBACK_DAYS": "4"},
            clear=False,
        ):
            root = Path(tmp)
            for value, stamp in (
                ("2026-09-22", "14-42-00"),
                ("2026-09-23", "14-43-00"),
                ("2026-09-24", "12-43-40"),
            ):
                (root / f"{value}-{stamp}.txt").write_text(
                    NEWS_TEMPLATE.format(date=value),
                    encoding="utf-8",
                )
            result = evaluate_source_coverage(
                target_date="2026-09-25",
                news_dir=root,
                min_ratio=0.75,
            )
            self.assertTrue(result["sufficient"])
            self.assertEqual(result["expected_dates"], [
                "2026-09-22",
                "2026-09-23",
                "2026-09-24",
            ])
            self.assertEqual(result["available_day_count"], 3)
            self.assertEqual(result["coverage_ratio"], 1.0)
            self.assertEqual(result["missing_dates"], [])

    def test_two_of_four_days_fails_default_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"NEWS_SOURCE_MODE": "recent_window", "NEWS_LOOKBACK_DAYS": "4"},
            clear=False,
        ):
            root = Path(tmp)
            for value in ("2026-08-23", "2026-08-24"):
                self._write_day(root, value)
            result = evaluate_source_coverage(
                target_date="2026-08-24",
                news_dir=root,
                min_ratio=0.75,
            )
            self.assertFalse(result["sufficient"])
            self.assertEqual(result["missing_dates"], ["2026-08-21", "2026-08-22"])

    def test_malformed_latest_file_does_not_fake_parseable_freshness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"NEWS_SOURCE_MODE": "scheduled_window", "NEWS_LOOKBACK_DAYS": "4"},
            clear=False,
        ):
            root = Path(tmp)
            for value in ("2026-09-22", "2026-09-23", "2026-09-24"):
                self._write_day(root, value)
            (root / "2026-09-25-18-00-00.txt").write_text(
                "this file has a date but no structured news contract\n",
                encoding="utf-8",
            )

            result = evaluate_source_coverage(
                target_date="2026-09-25",
                news_dir=root,
                min_ratio=0.75,
            )

            self.assertTrue(result["sufficient"])
            self.assertEqual(result["latest_detected_source_date"], "2026-09-25")
            self.assertEqual(result["latest_parseable_source_date"], "2026-09-24")
            self.assertEqual(result["source_staleness_basis"], "latest_parseable_source")

    def test_unparseable_window_day_is_not_counted_as_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"NEWS_SOURCE_MODE": "scheduled_window", "NEWS_LOOKBACK_DAYS": "4"},
            clear=False,
        ):
            root = Path(tmp)
            self._write_day(root, "2026-09-22")
            self._write_day(root, "2026-09-23")
            (root / "2026-09-24-18-00-00.txt").write_text(
                "Fecha: 2026-09-24\nnot parseable as a news digest\n",
                encoding="utf-8",
            )

            result = evaluate_source_coverage(
                target_date="2026-09-25",
                news_dir=root,
                min_ratio=0.75,
            )

            self.assertFalse(result["sufficient"])
            self.assertEqual(result["available_day_count"], 2)
            self.assertEqual(result["unparseable_dates"], ["2026-09-24"])
            self.assertEqual(result["coverage_ratio"], round(2 / 3, 4))

    def test_source_quality_is_observational_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"NEWS_SOURCE_MODE": "scheduled_window", "NEWS_LOOKBACK_DAYS": "4"},
            clear=False,
        ):
            root = Path(tmp)
            for value in ("2026-09-22", "2026-09-23", "2026-09-24"):
                self._write_day(root, value)

            result = evaluate_source_coverage(
                target_date="2026-09-25",
                news_dir=root,
                min_ratio=0.75,
            )

            quality = result["source_quality"]
            self.assertTrue(result["sufficient"])
            self.assertTrue(quality["observational_only"])
            self.assertGreaterEqual(quality["score"], 0)
            self.assertLessEqual(quality["score"], 100)
            self.assertEqual(quality["parseable_day_ratio"], 1.0)
            self.assertIn(quality["band"], {"low", "medium", "high"})


if __name__ == "__main__":
    unittest.main()
