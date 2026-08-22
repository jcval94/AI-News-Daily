from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.review_hub import build_site
from pipeline.review_media import association_label, media_filename, section_timeline


class ReviewHubTests(unittest.TestCase):
    def test_media_labels_encode_beat_and_evidence(self) -> None:
        section = {
            "position": 3,
            "section_key": "beat:criterio",
            "beat_id": "criterio_de_proceso",
            "evidence_ids": ["traces_benchmark", "audit_tool"],
        }
        self.assertEqual(
            association_label(section),
            "B03_criterio-de-proceso__E_traces-benchmark+audit-tool",
        )
        name = media_filename(
            {
                "slot_number": 12,
                "start_seconds": 24.2,
                "end_seconds": 29.8,
                "on_screen_text": "Rastro verificable",
            }
        )
        self.assertTrue(name.startswith("S012__0024-0030s__rastro-verificable"))

    def test_section_timeline_uses_spoken_word_counts(self) -> None:
        payload = {
            "sections": [
                {"section_key": "opening", "spoken_text": "uno dos tres cuatro cinco", "word_count": 5},
                {"section_key": "beat:x", "beat_id": "x", "evidence_ids": ["case"], "spoken_text": "seis siete ocho nueve diez", "word_count": 5},
            ]
        }
        timeline = section_timeline(payload, 2.5)
        self.assertEqual(timeline[0]["start_seconds"], 0)
        self.assertEqual(timeline[0]["end_seconds"], 2)
        self.assertEqual(timeline[1]["start_seconds"], 2)
        self.assertEqual(timeline[1]["end_seconds"], 4)

    def test_static_site_contains_validation_and_download_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode = root / "episode"
            media = root / "media"
            historical = root / "evals" / "editorial" / "runs" / "e2e-v1"
            episode.mkdir(parents=True)
            media.mkdir(parents=True)
            historical.mkdir(parents=True)
            (episode / "script.txt").write_text("Este es un guion de prueba con una pregunta final.", encoding="utf-8")
            (episode / "episode_plan.json").write_text(json.dumps({
                "topic_signature": "Criterio y conocimiento verificable",
                "central_question": "¿Qué cuenta como descubrimiento?",
                "thesis": "Una respuesta no basta.",
                "closing_question": "¿Qué verificarías?",
                "narrative_arc": {
                    "opening_belief": "Una respuesta clara parece suficiente.",
                    "central_mystery": "¿Dónde quedó la evidencia?",
                    "narrative_turn": "El problema es verificar, no responder.",
                    "evolved_thesis": "El conocimiento requiere un rastro auditable.",
                    "final_payoff": "La claridad deja de ser la meta.",
                    "recurring_motif": "la luz verde",
                    "emotional_peak": "delegar criterio",
                },
                "evidence": [{"evidence_id": "case", "selected_news_index": 1}],
                "beats": [{"beat_id": "turn", "kind": "turn", "estimated_minutes": 2, "purpose": "Reencuadrar la pregunta", "evidence_ids": ["case"]}],
            }), encoding="utf-8")
            (episode / "script_sections.json").write_text(json.dumps({"sections": []}), encoding="utf-8")
            (episode / "reviews.json").write_text(json.dumps({
                "gate": {"duration_seconds": 480},
                "best_candidate": {"iteration": 2, "judged_unique_script_count": 2},
                "editorial": {"score": 7.1, "approved": False},
                "seo_master": {"score": 8.9, "approved": True},
                "youtube_attention_master": {"score": 7.6, "approved": False},
                "voice_humanity": {"score": 8.1, "approved": False, "ai_smell_risk": "medium"},
            }), encoding="utf-8")
            (episode / "run_state.json").write_text(json.dumps({"episode_date": "2026-08-21", "status": "script_not_approved", "publishable": False}), encoding="utf-8")
            (episode / "selected_news.json").write_text(json.dumps({"items": [{"title": "Caso", "source": "Fuente", "url_quality": "article", "news_id": "x", "url": "https://example.com"}]}), encoding="utf-8")
            for name in ("novelty_check.json", "execution_trace.json"):
                (episode / name).write_text("{}", encoding="utf-8")
            (media / "manifest.json").write_text("[]", encoding="utf-8")
            (media / "plan.json").write_text("{}", encoding="utf-8")
            (media / "credits.md").write_text("# Credits\n", encoding="utf-8")
            media_zip = root / "multimedia.zip"
            media_zip.write_bytes(b"zip")
            regression = root / "editorial-regression.json"
            regression.write_text(json.dumps({"structural_pass": True}), encoding="utf-8")
            historical_script = historical / "script.txt"
            historical_script.write_text("Viejo", encoding="utf-8")
            cases = root / "evals" / "editorial" / "cases.json"
            cases.parent.mkdir(parents=True, exist_ok=True)
            cases.write_text(json.dumps({"cases": [{
                "case_id": "e2e-v1-2026-08-21",
                "workflow_run_id": 1,
                "script_path": "evals/editorial/runs/e2e-v1/script.txt",
                "human": {"publishable": False, "rejection_reasons": ["Plano"]},
            }]}), encoding="utf-8")
            output = root / "site"
            index = build_site(
                episode_dir=episode,
                media_dir=media,
                media_zip=media_zip,
                regression_path=regression,
                cases_path=cases,
                output_dir=output,
                run_id="12345",
            )
            text = index.read_text(encoding="utf-8")
            self.assertIn("2026-08-21-run-12345", text)
            self.assertIn("Descargar multimedia ZIP", text)
            self.assertIn("Guiones anteriores", text)
            self.assertTrue((output / "downloads" / "multimedia.zip").exists())


if __name__ == "__main__":
    unittest.main()
