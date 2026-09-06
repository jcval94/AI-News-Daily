from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from pipeline.news import parse_news_file, resolve_news_file, source_date_from_path, stable_news_id


class NewsParserTests(unittest.TestCase):
    def assertOpaqueIds(self, items) -> None:  # noqa: N802 - unittest helper style
        for item in items:
            self.assertRegex(item.news_id, r"^n_[0-9a-f]{16}$")
            self.assertNotIn(item.date.split(",", 1)[0], item.news_id)

    def test_parser_owns_provenance_and_flags_generic_urls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-08-21.txt"
            path.write_text(
                "# Noticias\n\n## 1. Caso uno\nFecha: 2026-08-20\nFuente: Fuente A\nEnlace: https://example.com/blog\nCategoría: agentes\nResumen: Resumen uno\nPor qué importa: Importa uno\n\n## 2. Caso dos\nFuente: Fuente B\nEnlace: https://example.com/news/specific-story\nResumen: Resumen dos\nPor qué importa: Importa dos\n",
                encoding="utf-8",
            )
            items = parse_news_file(path)
            self.assertOpaqueIds(items)
            self.assertEqual(len({item.news_id for item in items}), 2)
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
            self.assertOpaqueIds(items)
            self.assertEqual(items[0].title, "Caso real del repositorio")
            self.assertEqual(items[0].date, "19/08/2026, 12:10 ET")
            self.assertEqual(items[0].date_origin, "field")
            self.assertEqual(items[0].summary, "Un resumen preservado tal como llegó.")
            self.assertEqual(items[0].source_locator, "2026-08-20.txt#item-1")
            self.assertEqual(items[0].url_quality, "article")

    def test_current_timestamped_digest_blocks_are_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-09-01-08-23-09.txt"
            path.write_text(
                "# Noticias de Inteligencia Artificial — 2026-09-01 08:23:09 America/Mexico_City\n\n"
                "Título: Primer caso\n"
                "Fecha: 2026-09-01\n"
                "Fuente: Reuters\n"
                "Enlace: https://example.com/one\n"
                "Resumen breve: Resumen uno.\n"
                "Por qué importa: Importa uno.\n"
                "Categoría: agentes\n\n---\n\n"
                "Título: Segundo caso\n"
                "Fecha: 2026-09-01\n"
                "Fuente: Nature\n"
                "Enlace: https://example.com/two\n"
                "Resumen breve: Resumen dos.\n"
                "Por qué importa: Importa dos.\n"
                "Categoría: investigación\n",
                encoding="utf-8",
            )
            items = parse_news_file(path)
            self.assertOpaqueIds(items)
            self.assertEqual(items[0].title, "Primer caso")
            self.assertEqual(items[0].source_file, "2026-09-01-08-23-09.txt")
            self.assertEqual(items[0].date, "2026-09-01")
            self.assertEqual(items[1].summary, "Resumen dos.")
            self.assertEqual(source_date_from_path(path), "2026-09-01")

    def test_news_id_is_stable_across_timestamped_and_canonical_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = (
                "Título: El mismo caso\n"
                "Fecha: 2026-09-01\n"
                "Fuente: Reuters\n"
                "Enlace: https://example.com/same\n"
                "Resumen breve: Mismo contenido.\n"
                "Por qué importa: Prueba identidad.\n"
            )
            timestamped = root / "2026-09-01-08-23-09.txt"
            canonical = root / "2026-09-01.txt"
            timestamped.write_text(body, encoding="utf-8")
            canonical.write_text(body, encoding="utf-8")
            self.assertEqual(
                parse_news_file(timestamped)[0].news_id,
                parse_news_file(canonical)[0].news_id,
            )

    def test_stable_news_id_does_not_encode_reported_date(self) -> None:
        first = stable_news_id(
            title="Caso",
            source="Fuente",
            url="https://example.com/case",
            item_index=1,
        )
        self.assertRegex(first, r"^n_[0-9a-f]{16}$")
        self.assertFalse(re.search(r"\d{4}-\d{2}-\d{2}", first))

    def test_resolver_prefers_canonical_then_latest_timestamped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            early = root / "2026-09-01-08-00-00.txt"
            late = root / "2026-09-01-09-00-00.txt"
            early.write_text("early", encoding="utf-8")
            late.write_text("late", encoding="utf-8")
            self.assertEqual(resolve_news_file(root, "2026-09-01"), late)
            canonical = root / "2026-09-01.txt"
            canonical.write_text("canonical", encoding="utf-8")
            self.assertEqual(resolve_news_file(root, "2026-09-01"), canonical)

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
            path.write_text("Texto libre sin contrato editorial", encoding="utf-8")
            with self.assertRaises(ValueError):
                parse_news_file(path)

    def test_title_block_without_source_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-09-01-08-23-09.txt"
            path.write_text("Título: incompleto\nFecha: 2026-09-01\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                parse_news_file(path)


if __name__ == "__main__":
    unittest.main()
