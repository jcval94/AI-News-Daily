from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.source_coverage import evaluate_source_coverage, materialize_canonical_sources


NEWS_TEMPLATE = """## 1. Example AI development
Fecha: {date}
Fuente: Example Source
Enlace: https://example.com/{date}
Categoría: AI
Resumen: Example structured news item.
Por qué importa: It is useful for testing source coverage.
"""

TITLE_BLOCK_TEMPLATE = """Título: Example AI development
Fecha: {date}
Fuente: Example Source
Enlace: https://example.com/{date}
Categoría: AI
Resumen breve: Example structured news item.
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

    def test_timestamped_daily_sources_satisfy_coverage_and_are_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"NEWS_SOURCE_MODE": "scheduled_window"},
            clear=False,
        ):
            root = Path(tmp)
            for value, clock in (
                ("2026-09-01", "08-23-09"),
                ("2026-09-02", "08-35-24"),
                ("2026-09-03", "08-45-35"),
            ):
                (root / f"{value}-{clock}.txt").write_text(
                    TITLE_BLOCK_TEMPLATE.format(date=value), encoding="utf-8"
                )
            result = evaluate_source_coverage(
                target_date="2026-09-04",
                news_dir=root,
                min_ratio=0.75,
            )
            self.assertTrue(result["sufficient"])
            self.assertEqual(result["available_day_count"], 3)
            self.assertEqual(result["missing_dates"], [])
            self.assertEqual(
                result["resolved_files"],
                {
                    "2026-09-01": "2026-09-01-08-23-09.txt",
                    "2026-09-02": "2026-09-02-08-35-24.txt",
                    "2026-09-03": "2026-09-03-08-45-35.txt",
                },
            )

            created = materialize_canonical_sources(root, result)
            self.assertEqual(
                created,
                ["2026-09-01.txt", "2026-09-02.txt", "2026-09-03.txt"],
            )
            for value in ("2026-09-01", "2026-09-02", "2026-09-03"):
                self.assertTrue((root / f"{value}.txt").exists())

    def test_live_repository_sep4_window_is_now_sufficient(self) -> None:
        with patch.dict(os.environ, {"NEWS_SOURCE_MODE": "scheduled_window"}, clear=False):
            result = evaluate_source_coverage(
                target_date="2026-09-04",
                news_dir=Path("news"),
                min_ratio=0.75,
            )
        self.assertTrue(result["sufficient"])
        self.assertEqual(result["available_day_count"], 3)
        self.assertEqual(result["expected_day_count"], 3)
        self.assertEqual(result["coverage_ratio"], 1.0)
        self.assertGreater(result["item_count"], 0)


if __name__ == "__main__":
    unittest.main()
