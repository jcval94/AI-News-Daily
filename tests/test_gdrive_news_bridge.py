from __future__ import annotations

import base64
import hashlib
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from pipeline.gdrive_news_bridge import process_envelope

TZ = ZoneInfo("America/Mexico_City")
REPO = "jcval94/AI-News-Daily"


def story(i: int, item_date: str = "2026-10-01") -> str:
    return (
        f"Título: Caso {i} con cambio relevante\n"
        f"Fecha: {item_date}\n"
        f"Fuente: Fuente {i}\n"
        f"Enlace: https://example.com/news/caso-{i}\n"
        "Resumen breve: Este es un resumen factual suficientemente extenso para validar el contrato del digest diario, distinguiendo lo ocurrido de cualquier interpretación posterior y evitando afirmaciones no verificadas.\n"
        "Por qué importa: La problemática general muestra un cambio estructural concreto y la tensión enfrenta capacidad nueva contra una restricción humana real. ¿Qué cambia cuando esta capacidad deja de ser excepcional y pasa a integrarse en decisiones cotidianas? La consecuencia humana afecta la forma de trabajar y decidir. Hipótesis editorial: provisionalmente, el valor podría desplazarse hacia supervisión y criterio. Qué habría que investigar: evidencia independiente, estadísticas, experimentos, casos reales, expertos y contraargumentos antes de sostener la hipótesis.\n"
        "Categoría: investigación\n"
    )


def digest(stamp: str = "2026-10-01 18:45:00") -> str:
    body = [f"# AI News Daily — {stamp} America/Mexico_City", ""]
    for i in range(1, 6):
        body.append(story(i))
        body.append("")
    return "\n".join(body).strip()


def envelope(path: Path, payload: str, *, repo: str = REPO, target_path: str = "news/2026-10-01-18-45-00.txt") -> None:
    data = payload.encode("utf-8")
    body = "\n".join(
        [
            "format=base64-payload-v1",
            "schema_version=1.0",
            "message_id=ai-news-daily.news.2026-10-01.184500",
            f"target_repo={repo}",
            f"target_path={target_path}",
            "content_type=text/plain",
            f"sha256={hashlib.sha256(data).hexdigest()}",
            f"payload_b64={base64.b64encode(data).decode('ascii')}",
            "",
        ]
    )
    path.write_text(body, encoding="utf-8")


class GDriveNewsBridgeTests(unittest.TestCase):
    @patch("pipeline.staged_news_issue.datetime")
    def test_valid_envelope_materializes_digest(self, mock_datetime) -> None:
        mock_datetime.now.return_value = datetime(2026, 10, 1, 18, 46, tzinfo=TZ)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_path = root / "envelope.txt"
            news = root / "news"
            envelope(env_path, digest())

            status, output, day, message_id = process_envelope(env_path, REPO, news)

            self.assertEqual(status, "created")
            self.assertEqual(day, "2026-10-01")
            self.assertEqual(message_id, "ai-news-daily.news.2026-10-01.184500")
            self.assertEqual(output, news / "2026-10-01-18-45-00.txt")
            self.assertTrue(output.exists())

    @patch("pipeline.staged_news_issue.datetime")
    def test_wrong_repo_is_rejected(self, mock_datetime) -> None:
        mock_datetime.now.return_value = datetime(2026, 10, 1, 18, 46, tzinfo=TZ)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_path = root / "envelope.txt"
            envelope(env_path, digest(), repo="jcval94/floor")
            with self.assertRaisesRegex(ValueError, "target_repo mismatch"):
                process_envelope(env_path, REPO, root / "news")

    @patch("pipeline.staged_news_issue.datetime")
    def test_header_and_target_path_must_match(self, mock_datetime) -> None:
        mock_datetime.now.return_value = datetime(2026, 10, 1, 18, 46, tzinfo=TZ)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_path = root / "envelope.txt"
            envelope(
                env_path,
                digest("2026-10-01 18:44:00"),
                target_path="news/2026-10-01-18-45-00.txt",
            )
            with self.assertRaisesRegex(ValueError, "encabezado"):
                process_envelope(env_path, REPO, root / "news")

    @patch("pipeline.staged_news_issue.datetime")
    def test_existing_digest_is_idempotent(self, mock_datetime) -> None:
        mock_datetime.now.return_value = datetime(2026, 10, 1, 18, 46, tzinfo=TZ)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            news = root / "news"
            news.mkdir()
            existing = news / "2026-10-01-18-40-00.txt"
            existing.write_text(digest("2026-10-01 18:40:00") + "\n", encoding="utf-8")
            env_path = root / "envelope.txt"
            envelope(env_path, digest())

            status, output, _, _ = process_envelope(env_path, REPO, news)

            self.assertEqual(status, "already_exists")
            self.assertEqual(output, existing)


if __name__ == "__main__":
    unittest.main()
