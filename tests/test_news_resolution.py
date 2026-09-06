from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pipeline.news import parse_news_file
from pipeline.news_resolution import (
    candidate_news_files,
    collect_available_news,
    install,
    load_news_for_date,
)
from pipeline.source_coverage import evaluate_source_coverage


NEWS_TEMPLATE = """## 1. Example AI development
Fecha: {date}
Fuente: Example Source
Enlace: https://example.com/{slug}
Categoría: investigación
Resumen breve: Example structured news item.
Por qué importa: It is useful for testing timestamped source resolution.
"""

CURRENT_DAILY_TEMPLATE = """# AI News Daily — {date}

Título: First current-format story
Fecha: {date}
Fuente: Primary Source
Enlace: https://example.com/first
Resumen breve: First factual summary.
Por qué importa: First editorial interpretation.
Categoría: investigación

Título: Second current-format story
Fecha: {date}
Fuente: Official Documentation
Enlace: https://example.com/second
Resumen breve: Second factual summary.
Por qué importa: Second editorial interpretation.
Categoría: producto
"""


class NewsResolutionTests(unittest.TestCase):
    def _write(self, root: Path, name: str, item_date: str, slug: str = "story") -> Path:
        path = root / name
        path.write_text(
            NEWS_TEMPLATE.format(date=item_date, slug=slug),
            encoding="utf-8",
        )
        return path

    def test_timestamped_source_is_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = self._write(
                root,
                "2026-09-05-08-36-19.txt",
                "2026-09-05",
            )
            path, items = load_news_for_date(root, date(2026, 9, 5))
            self.assertEqual(path, expected)
            self.assertEqual(len(items), 1)

    def test_latest_timestamped_source_wins_over_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "2026-09-05.txt", "2026-09-05", "legacy")
            self._write(root, "2026-09-05-08-00-00.txt", "2026-09-05", "older")
            newest = self._write(root, "2026-09-05-09-30-00.txt", "2026-09-05", "newest")
            candidates = candidate_news_files(root, date(2026, 9, 5))
            self.assertEqual(candidates[0], newest)
            path, items = load_news_for_date(root, date(2026, 9, 5))
            self.assertEqual(path, newest)
            self.assertIn("newest", items[0].url)

    def test_empty_or_malformed_latest_source_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fallback = self._write(
                root,
                "2026-09-05-08-00-00.txt",
                "2026-09-05",
                "fallback",
            )
            (root / "2026-09-05-09-00-00.txt").write_text("not structured", encoding="utf-8")
            (root / "2026-09-05-10-00-00.txt").write_text("\n", encoding="utf-8")
            path, items = load_news_for_date(root, date(2026, 9, 5))
            self.assertEqual(path, fallback)
            self.assertEqual(len(items), 1)

    def test_current_titulo_contract_parses_multiple_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "2026-09-06-08-20-02.txt"
            path.write_text(
                CURRENT_DAILY_TEMPLATE.format(date="2026-09-06"),
                encoding="utf-8",
            )
            items = parse_news_file(path)
            self.assertEqual(len(items), 2)
            self.assertEqual(items[0].title, "First current-format story")
            self.assertEqual(items[1].category, "producto")
            self.assertEqual(items[0].source_file, path.name)

    def test_timestamped_filename_supplies_date_when_field_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-09-06-08-20-02.txt"
            path.write_text(
                """Título: Story without explicit date\nFuente: Example\nEnlace: https://example.com/story\nResumen breve: Summary.\nPor qué importa: Interpretation.\nCategoría: investigación\n""",
                encoding="utf-8",
            )
            item = parse_news_file(path)[0]
            self.assertEqual(item.date, "2026-09-06")
            self.assertEqual(item.date_origin, "source_file")

    def test_source_coverage_counts_timestamped_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"NEWS_SOURCE_MODE": "recent_window", "NEWS_LOOKBACK_DAYS": "4"},
            clear=False,
        ):
            root = Path(tmp)
            for value in ("2026-09-03", "2026-09-04", "2026-09-05"):
                self._write(root, f"{value}-08-00-00.txt", value, value)
            result = evaluate_source_coverage(
                target_date="2026-09-05",
                news_dir=root,
                min_ratio=0.75,
            )
            self.assertTrue(result["sufficient"])
            self.assertEqual(result["available_day_count"], 3)
            self.assertEqual(result["missing_dates"], ["2026-09-02"])
            self.assertTrue(all(name.endswith("-08-00-00.txt") for name in result["available_files"]))

    def test_runtime_install_replaces_legacy_collector(self) -> None:
        base = SimpleNamespace(collect_available_news=lambda *_: "legacy")
        installed = install(base)
        self.assertIs(installed.collect_available_news, collect_available_news)


if __name__ == "__main__":
    unittest.main()
