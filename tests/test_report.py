from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from pipeline.report import build_report


class ReportTests(unittest.TestCase):
    def test_report_uses_run_state_and_hashes_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            news = root / "news"
            scripts = root / "scripts"
            multimedia = root / "multimedia"
            editorial = root / "editorial"
            news.mkdir()
            editorial.mkdir()
            (editorial / "voice_profile.md").write_text("voz", encoding="utf-8")
            (editorial / "discourse_profile.md").write_text("discurso", encoding="utf-8")
            episode_dir = scripts / "2026-08-21"
            episode_dir.mkdir(parents=True)
            (news / "2026-08-20.txt").write_text(
                "Título: Prueba estructurada\n"
                "Fecha: 2026-08-20\n"
                "Fuente: test\n"
                "Enlace: https://example.com/article\n"
                "Resumen breve: Esta es una noticia estructurada para probar el reporte.\n"
                "Por qué importa: Verifica que el mismo resolver de producción alimente observabilidad.\n"
                "Categoría: modelos\n",
                encoding="utf-8",
            )
            (episode_dir / "run_state.json").write_text(
                json.dumps({"status": "script_not_approved", "reason": "voice"}),
                encoding="utf-8",
            )
            (episode_dir / "execution_trace.json").write_text(
                json.dumps({"agent_calls": [], "refinement_iterations": []}),
                encoding="utf-8",
            )
            (episode_dir / "episode_plan.json").write_text(
                json.dumps(
                    {
                        "central_question": "¿Qué delegamos cuando delegamos razonamiento?",
                        "thesis": "La herramienta también cambia hábitos.",
                        "hook": "¿Y si pensar menos fuera el verdadero costo?",
                        "target_duration_minutes": 9.0,
                        "stories": [{"selected_news_index": 1}],
                        "closing_question": "¿Qué no delegarías?",
                    }
                ),
                encoding="utf-8",
            )
            (episode_dir / "reviews.json").write_text(
                json.dumps(
                    {
                        "approved_for_multimedia": False,
                        "voice_humanity": {
                            "approved": False,
                            "score": 7.8,
                            "voice_fidelity": 7.5,
                            "intellectual_depth": 8.0,
                            "human_relevance": 8.2,
                            "analogy_quality": 7.0,
                            "ai_smell_risk": "medium",
                            "problems": ["too generic"],
                            "improvements": ["stronger point of view"],
                        },
                    }
                ),
                encoding="utf-8",
            )
            report = build_report(
                date(2026, 8, 21),
                news,
                scripts,
                multimedia,
                "script_not_approved",
                editorial,
            )
            self.assertEqual(report["status"], "script_not_approved")
            self.assertEqual(
                report["source_window"]["available_files"][0]["name"],
                "2026-08-20.txt",
            )
            self.assertTrue(report["source_window"]["available_files"][0]["sha256"])
            self.assertTrue(report["artifacts"]["run_state"]["sha256"])
            self.assertEqual(report["schema_version"], 9)
            self.assertEqual(report["artifacts"]["run_state"]["path"], "scripts/2026-08-21/run_state.json")
            self.assertNotIn(".pipeline-runs", report["artifacts"]["run_state"]["path"])
            self.assertEqual(
                report["editorial_direction"]["target_duration_minutes"], 9.0
            )
            self.assertEqual(
                report["judges"]["voice_humanity"]["ai_smell_risk"], "medium"
            )
            self.assertTrue(report["artifacts"]["voice_profile"]["sha256"])


    def test_report_resolves_timestamped_news_like_source_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            news = root / "news"
            scripts = root / "scripts"
            multimedia = root / "multimedia"
            editorial = root / "editorial"
            news.mkdir()
            editorial.mkdir()
            episode_dir = scripts / "2026-08-21"
            episode_dir.mkdir(parents=True)
            (news / "2026-08-20-14-30-00.txt").write_text(
                "Título: Fuente timestamped\n"
                "Fecha: 2026-08-20\n"
                "Fuente: test\n"
                "Enlace: https://example.com/timestamped\n"
                "Resumen breve: Fuente válida con hora en el nombre.\n"
                "Por qué importa: Evita contradicción entre source coverage y run report.\n"
                "Categoría: sociedad\n",
                encoding="utf-8",
            )
            (episode_dir / "run_state.json").write_text(
                json.dumps({"status": "script_not_approved"}),
                encoding="utf-8",
            )
            report = build_report(
                date(2026, 8, 21),
                news,
                scripts,
                multimedia,
                "script_not_approved",
                editorial,
            )
            names = [item["name"] for item in report["source_window"]["available_files"]]
            self.assertIn("2026-08-20-14-30-00.txt", names)


if __name__ == "__main__":
    unittest.main()
