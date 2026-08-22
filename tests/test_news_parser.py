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

    def test_existing_report_format_is_parsed_without_rewriting_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-08-20.txt"
            path.write_text(
                "NOTICIAS DE IA — 2026-08-20\n\n"
                "1) Caso real del repositorio\n"
                "Fecha: 19/08/2026, 12:10 ET\n"
                "Fuente: Fuente primaria / PR Newswire\n"
                "Enlace: https://example.com/releases/caso-real.html\n"
                "Categoría: investigación\n"
                "Resumen breve: Un resumen preservado tal como llegó.\n"
                "Por qué importa: Permite probar el parser real.\n\n"
                "2) Segundo caso\n"
                "Fecha: 19/08/2026, 13:00 ET\n"
                "Fuente: Otra fuente\n"
                "Enlace: https://example.com/releases/segundo.html\n"
                "Categoría: agentes\n"
                "Resumen breve: Otro resumen.\n"
                "Por qué importa: Otro impacto.\n\nFIN DEL INFORME\n",
                encoding="utf-8",
            )
            items = parse_news_file(path)
            self.assertEqual([item.news_id for item in items], ["2026-08-20:1", "2026-08-20:2"])
            self.assertEqual(items[0].title, "Caso real del repositorio")
            self.assertEqual(items[0].date, "19/08/2026, 12:10 ET")
            self.assertEqual(items[0].date_origin, "field")
            self.assertEqual(items[0].summary, "Un resumen preservado tal como llegó.")
            self.assertEqual(items[0].source_locator, "2026-08-20.txt#item-1")
            self.assertEqual(items[0].url_quality, "article")

    def test_duplicate_item_indices_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-08-21.txt"
            path.write_text(
                "1) Uno\nFuente: A\n\n1) Dos\nFuente: B\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                parse_news_file(path)

    def test_unstructured_file_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-08-21.txt"
            path.write_text("Título: sin heading estructurado", encoding="utf-8")
            with self.assertRaises(ValueError):
                parse_news_file(path)


if __name__ == "__main__":
    unittest.main()
