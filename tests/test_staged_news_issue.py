from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from pipeline.staged_news_issue import process_event

TZ = ZoneInfo("America/Mexico_City")


def story(
    i: int,
    *,
    title: str | None = None,
    url: str | None = None,
    summary_prefix: str = "",
    item_date: str = "2026-09-26",
    variant: str = "current",
) -> str:
    return (
        f"Título: {title or f'Caso {variant} {i} con cambio relevante'}\n"
        f"Fecha: {item_date}\n"
        f"Fuente: Fuente {variant} {i}\n"
        f"Enlace: {url or f'https://example.com/news/{variant}-caso-{i}'}\n"
        f"Resumen breve: {summary_prefix}Este es un resumen factual suficientemente extenso para validar el contrato del digest diario, distinguiendo lo ocurrido de cualquier interpretación posterior y evitando afirmaciones no verificadas.\n"
        "Por qué importa: La problemática general muestra un cambio estructural concreto y la tensión enfrenta capacidad nueva contra una restricción humana real. ¿Qué cambia cuando esta capacidad deja de ser excepcional y pasa a integrarse en decisiones cotidianas? La consecuencia humana afecta la forma de trabajar y decidir. Hipótesis editorial: provisionalmente, el valor podría desplazarse hacia supervisión y criterio. Qué habría que investigar: evidencia independiente, estadísticas, experimentos, casos reales, expertos y contraargumentos antes de sostener la hipótesis.\n"
        "Categoría: investigación\n"
    )


def digest(
    stamp: str = "2026-09-26 08:00:00",
    *,
    first_title: str | None = None,
    first_url: str | None = None,
    first_summary_prefix: str = "",
    item_date: str = "2026-09-26",
    variant: str = "current",
) -> str:
    body = [f"# AI News Daily — {stamp} America/Mexico_City", ""]
    for i in range(1, 6):
        body.append(
            story(
                i,
                title=first_title if i == 1 else None,
                url=first_url if i == 1 else None,
                summary_prefix=first_summary_prefix if i == 1 else "",
                item_date=item_date,
                variant=variant,
            )
        )
        body.append("")
    return "\n".join(body).strip()


def event(path: Path, body: str, stamp: str = "2026-09-26 08:00:00") -> None:
    path.write_text(
        json.dumps(
            {
                "issue": {
                    "title": f"AI_NEWS_STAGING — {stamp} America/Mexico_City",
                    "body": body,
                }
            }
        ),
        encoding="utf-8",
    )


class StagedNewsIssueTests(unittest.TestCase):
    @patch("pipeline.staged_news_issue.datetime")
    def test_thin_existing_candidate_does_not_block_valid_recovery(self, mock_datetime) -> None:
        mock_datetime.now.return_value = datetime(2026, 9, 26, 8, 1, tzinfo=TZ)
        with tempfile.TemporaryDirectory() as tmp:
            news = Path(tmp) / "news"
            news.mkdir()
            thin = f"# AI News Daily — 2026-09-26 07:00:00 America/Mexico_City\n\n{story(1)}"
            existing = news / "2026-09-26-07-00-00.txt"
            existing.write_text(thin, encoding="utf-8")
            ev = Path(tmp) / "event.json"
            event(ev, digest())
            status, output = process_event(ev, news)
            self.assertEqual(status, "created")
            self.assertNotEqual(output, existing)
            self.assertEqual(existing.read_text(encoding="utf-8"), thin)

    @patch("pipeline.staged_news_issue.datetime")
    def test_materializes_one_valid_digest(self, mock_datetime) -> None:
        mock_datetime.now.return_value = datetime(2026, 9, 26, 8, 1, tzinfo=TZ)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            news = root / "news"
            ev = root / "event.json"
            event(ev, digest())
            status, output = process_event(ev, news)
            self.assertEqual(status, "created")
            self.assertEqual(output.name, "2026-09-26-08-00-00.txt")
            self.assertTrue(output.exists())

    @patch("pipeline.staged_news_issue.datetime")
    def test_existing_digest_makes_ingest_idempotent(self, mock_datetime) -> None:
        mock_datetime.now.return_value = datetime(2026, 9, 26, 8, 1, tzinfo=TZ)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            news = root / "news"
            news.mkdir()
            existing = news / "2026-09-26-07-59-00.txt"
            existing.write_text(digest("2026-09-26 07:59:00") + "\n", encoding="utf-8")
            ev = root / "event.json"
            event(ev, digest())
            status, output = process_event(ev, news)
            self.assertEqual(status, "already_exists")
            self.assertEqual(output, existing)

    @patch("pipeline.staged_news_issue.datetime")
    def test_previous_day_is_allowed_for_bounded_recovery(self, mock_datetime) -> None:
        mock_datetime.now.return_value = datetime(2026, 9, 28, 8, 1, tzinfo=TZ)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            news = root / "news"
            ev = root / "event.json"
            event(
                ev,
                digest(
                    "2026-09-27 23:55:00",
                    item_date="2026-09-27",
                    variant="late-recovery",
                ),
                stamp="2026-09-27 23:55:00",
            )
            status, output = process_event(ev, news)
            self.assertEqual(status, "created")
            self.assertEqual(output.name, "2026-09-27-23-55-00.txt")

    @patch("pipeline.staged_news_issue.datetime")
    def test_older_than_previous_day_is_rejected(self, mock_datetime) -> None:
        mock_datetime.now.return_value = datetime(2026, 9, 28, 8, 1, tzinfo=TZ)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            news = root / "news"
            ev = root / "event.json"
            event(
                ev,
                digest(
                    "2026-09-26 08:00:00",
                    item_date="2026-09-26",
                    variant="too-old",
                ),
                stamp="2026-09-26 08:00:00",
            )
            with self.assertRaisesRegex(ValueError, "día anterior"):
                process_event(ev, news)

    @patch("pipeline.staged_news_issue.datetime")
    def test_recent_duplicate_requires_material_update(self, mock_datetime) -> None:
        mock_datetime.now.return_value = datetime(2026, 9, 26, 8, 1, tzinfo=TZ)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            news = root / "news"
            news.mkdir()
            old_title = "Caso repetido"
            old_url = "https://example.com/news/repetido"
            old = digest(
                "2026-09-25 08:00:00",
                first_title=old_title,
                first_url=old_url,
                item_date="2026-09-25",
                variant="previous",
            )
            (news / "2026-09-25-08-00-00.txt").write_text(old + "\n", encoding="utf-8")

            ev = root / "event.json"
            event(ev, digest(first_title=old_title, first_url=old_url, variant="new"))
            with self.assertRaisesRegex(ValueError, "repetición reciente"):
                process_event(ev, news)

            event(
                ev,
                digest(
                    first_title=old_title,
                    first_url=old_url,
                    first_summary_prefix="Esta es una actualización material: ",
                    variant="new",
                ),
            )
            status, _ = process_event(ev, news)
            self.assertEqual(status, "created")


if __name__ == "__main__":
    unittest.main()
