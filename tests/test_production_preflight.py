from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from pipeline.production_preflight import build_preflight, next_scheduled_production_date


NEWS = """## 1. Example AI development
Fecha: {date}
Fuente: Example Source
Enlace: https://example.com/{date}/story
Categoría: AI
Resumen: Example structured news item.
Por qué importa: It is useful for testing production readiness.
"""


def _memory() -> dict:
    return {
        "id": "verified-case",
        "title": "A verified unusual historical case",
        "one_liner": "A surprising case whose structure can illuminate a modern problem.",
        "summary": "A sufficiently detailed verified summary that can be safely used as contextual evidence.",
        "verified_claims": ["A source-backed fact."],
        "uncertainties": ["The analogy does not establish identical causality."],
        "sources": ["https://example.org/source"],
        "period": "1980s",
        "location": "Example",
        "domains": ["history"],
        "mechanisms": ["agility_vs_scale"],
        "useful_for": ["small systems versus large systems"],
        "analogy_mapping": "Map the structural trade-off, not the literal historical details.",
        "analogy_limits": "Do not claim the two domains are causally equivalent.",
        "surprise_score": 9,
        "explanatory_score": 9,
        "analogy_potential": 9,
        "visual_score": 8,
        "sourceability_score": 8,
        "source_quality_score": 9,
        "confidence": 9,
        "semantic_duplicate_risk": "low",
        "source_kind": "scheduled_research",
        "created_at": "2026-09-24",
        "status": "approved",
    }


class ProductionPreflightTests(unittest.TestCase):
    def _repo(self, root: Path) -> None:
        (root / "news").mkdir()
        (root / "editorial").mkdir()
        (root / "editorial" / "narrative_memory.jsonl").write_text(
            json.dumps(_memory()) + "\n",
            encoding="utf-8",
        )

    def test_next_scheduled_date(self) -> None:
        self.assertEqual(next_scheduled_production_date(date(2026, 9, 28)), date(2026, 9, 29))
        self.assertEqual(next_scheduled_production_date(date(2026, 9, 29)), date(2026, 9, 29))
        self.assertEqual(next_scheduled_production_date(date(2026, 9, 30)), date(2026, 10, 2))

    def test_ready_preflight_has_no_production_side_effect_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            "os.environ",
            {"NEWS_SOURCE_MODE": "scheduled_window"},
            clear=False,
        ):
            root = Path(tmp)
            self._repo(root)
            for value in ("2026-09-25", "2026-09-26", "2026-09-27", "2026-09-28"):
                (root / "news" / f"{value}.txt").write_text(
                    NEWS.format(date=value),
                    encoding="utf-8",
                )

            report = build_preflight(
                repo_root=root,
                target_date=date(2026, 9, 29),
                openai_configured=True,
                pexels_configured=False,
                youtube_configured=False,
            )

            self.assertEqual(report["status"], "ready")
            self.assertTrue(report["side_effect_free"])
            self.assertEqual(report["model_calls"], 0)
            self.assertEqual(report["production_state_writes"], 0)
            self.assertEqual(report["memory_usage_writes"], 0)
            self.assertGreater(report["readiness_score"], 0)
            self.assertTrue(report["source_quality"]["observational_only"])

    def test_missing_openai_secret_marks_at_risk_without_changing_source_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            "os.environ",
            {"NEWS_SOURCE_MODE": "scheduled_window"},
            clear=False,
        ):
            root = Path(tmp)
            self._repo(root)
            for value in ("2026-09-25", "2026-09-26", "2026-09-27", "2026-09-28"):
                (root / "news" / f"{value}.txt").write_text(
                    NEWS.format(date=value),
                    encoding="utf-8",
                )

            report = build_preflight(
                repo_root=root,
                target_date=date(2026, 9, 29),
                openai_configured=False,
            )

            self.assertEqual(report["status"], "at_risk")
            self.assertTrue(report["hard_requirements"]["parseable_source_coverage"])
            self.assertFalse(report["hard_requirements"]["openai_configured"])

    def test_malformed_dated_sources_are_reported_as_unparseable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            "os.environ",
            {"NEWS_SOURCE_MODE": "scheduled_window"},
            clear=False,
        ):
            root = Path(tmp)
            self._repo(root)
            (root / "news" / "2026-09-25.txt").write_text(
                NEWS.format(date="2026-09-25"),
                encoding="utf-8",
            )
            (root / "news" / "2026-09-26.txt").write_text(
                "Fecha: 2026-09-26\nmalformed\n",
                encoding="utf-8",
            )

            report = build_preflight(
                repo_root=root,
                target_date=date(2026, 9, 29),
                openai_configured=True,
            )

            self.assertEqual(report["status"], "at_risk")
            self.assertIn("2026-09-26", report["source_coverage"]["unparseable_dates"])


if __name__ == "__main__":
    unittest.main()
