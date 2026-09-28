from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from pipeline.news_ingestion_health import evaluate_daily_ingestion


ITEM = """Título: Noticia {n}
Fecha: 2026-09-28
Fuente: Test
Enlace: https://example.com/{n}
Resumen breve: Resumen suficientemente estructurado para una noticia de prueba número {n} en el watchdog diario.
Por qué importa: ¿Qué cambia cuando una señal operativa deja de ser visible? Este texto representa una explicación editorial suficientemente larga para el parser de pruebas y permite validar que el watchdog cuente noticias reales sin confundir la existencia de un archivo con una entrada sana. Hipótesis editorial: la observabilidad reduce fallos silenciosos. Qué habría que investigar: incidencias, latencia y recuperación del sistema.
Categoría: agentes
"""


class NewsIngestionHealthTests(unittest.TestCase):
    def _write(self, root: Path, count: int) -> None:
        parts = [f"# AI News Daily — 2026-09-28 08:00:00 America/Mexico_City\n"]
        for n in range(1, count + 1):
            parts.append(ITEM.format(n=n))
        (root / "2026-09-28-08-00-00.txt").write_text("\n".join(parts), encoding="utf-8")

    def test_missing_day_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = evaluate_daily_ingestion(
                day=date(2026, 9, 28),
                news_dir=Path(tmp),
            )
        self.assertFalse(report["healthy"])
        self.assertEqual(report["status"], "missing")

    def test_five_parseable_items_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, 5)
            report = evaluate_daily_ingestion(
                day=date(2026, 9, 28),
                news_dir=root,
            )
        self.assertTrue(report["healthy"])
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["item_count"], 5)

    def test_thin_digest_is_visible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, 4)
            report = evaluate_daily_ingestion(
                day=date(2026, 9, 28),
                news_dir=root,
            )
        self.assertFalse(report["healthy"])
        self.assertEqual(report["status"], "thin")


if __name__ == "__main__":
    unittest.main()
