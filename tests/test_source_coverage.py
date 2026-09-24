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


if __name__ == "__main__":
    unittest.main()
