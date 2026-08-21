from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pipeline.news import parse_news_file


class NewsParserTests(unittest.TestCase):
    def test_parser_owns_provenance_and_flags_generic_urls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-08-21.txt"
            path.write_text(
                "# Noticias\n\n## 1. Caso uno\nFecha: 2026-08-20\nFuente: Fuente A\nEnlace: https://example.com/blog\nCategoría: agentes\nResumen: Resumen uno\nPor qué importa: Importa uno\n\n## 2. Caso dos\nFuente: Fuente B\nEnlace: https://example.com/news/specific-story\nResumen: Resumen dos\nPor qué importa: Importa dos\n",
                encoding="utf-8",
            )
            items = parse_news_file(path)
            self.assertEqual([item.news_id for item in items], ["2026-08-21:1", "2026-08-21:2"])
            self.assertEqual(items[0].source_locator, "2026-08-21.txt#item-1")
            self.assertEqual(items[0].url_quality, "generic")
            self.assertEqual(items[1].url_quality, "article")
            self.assertEqual(items[1].date, "2026-08-21")
            self.assertEqual(items[1].date_origin, "source_file")

    def test_unstructured_file_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-08-21.txt"
            path.write_text("Título: sin heading estructurado", encoding="utf-8")
            with self.assertRaises(ValueError):
                parse_news_file(path)


if __name__ == "__main__":
    unittest.main()
