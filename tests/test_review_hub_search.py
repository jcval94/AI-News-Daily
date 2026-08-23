from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.review_hub import build_site


class ReviewHubSearchTests(unittest.TestCase):
    def test_compact_hero_search_and_collapsed_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode = root / "episode"
            media = root / "media"
            episode.mkdir(parents=True)
            media.mkdir(parents=True)

            (episode / "script.txt").write_text(
                "La claridad no es lo mismo que la evidencia. Una prueba cambia lo que entendemos.",
                encoding="utf-8",
            )
            (episode / "episode_plan.json").write_text(
                json.dumps(
                    {
                        "topic_signature": "Cuando una respuesta parece conocimiento",
                        "central_question": "¿Qué convierte una respuesta en conocimiento verificable?",
                        "thesis": "Responder no basta.",
                        "closing_question": "¿Qué evidencia exigirías?",
                        "narrative_arc": {
                            "opening_belief": "Una respuesta clara parece suficiente.",
                            "central_mystery": "La evidencia puede faltar.",
                            "narrative_turn": "El problema es verificar.",
                            "evolved_thesis": "El conocimiento necesita un rastro auditable.",
                            "final_payoff": "La claridad deja de ser la meta.",
                            "recurring_motif": "la luz verde",
                            "emotional_peak": "delegar criterio",
                        },
                        "evidence": [{"evidence_id": "traces", "selected_news_index": 1}],
                        "beats": [
                            {
                                "beat_id": "turn",
                                "kind": "turn",
                                "estimated_minutes": 2,
                                "purpose": "Reencuadrar la pregunta hacia verificación.",
                                "evidence_ids": ["traces"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (episode / "reviews.json").write_text(
                json.dumps(
                    {
                        "gate": {"duration_seconds": 480},
                        "best_candidate": {"iteration": 2, "judged_unique_script_count": 2},
                        "editorial": {"score": 7.1, "approved": False, "problems": ["Falta tensión"]},
                        "seo_master": {"score": 8.9, "approved": True},
                        "youtube_attention_master": {"score": 7.6, "approved": False},
                        "voice_humanity": {"score": 8.1, "approved": False, "ai_smell_risk": "medium"},
                    }
                ),
                encoding="utf-8",
            )
            (episode / "run_state.json").write_text(
                json.dumps({"episode_date": "2026-08-21", "status": "script_not_approved", "publishable": False}),
                encoding="utf-8",
            )
            (episode / "selected_news.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "title": "TRACES benchmark",
                                "source": "Example",
                                "url_quality": "article",
                                "news_id": "2026-08-21:1",
                                "url": "https://example.com/traces",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            for name in ("script_sections.json", "novelty_check.json", "execution_trace.json"):
                (episode / name).write_text("{}", encoding="utf-8")

            (media / "manifest.json").write_text(
                json.dumps(
                    [
                        {
                            "file": "B00_opening/S001__0000-0004s__evidencia.mp4",
                            "asset_type": "video",
                            "mime_type": "video/mp4",
                            "visual_query": "evidence research footage",
                            "section_key": "opening",
                            "beat_id": "",
                            "start_seconds": 0,
                            "end_seconds": 3.5,
                            "provider": "pexels",
                            "license": "Pexels License",
                            "slot_priority": "opening_dense_media",
                            "preferred_asset_type": "video",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (media / "plan.json").write_text(
                json.dumps({"opening_media_count": 6, "opening_video_count": 6}), encoding="utf-8"
            )
            (media / "credits.md").write_text("# Credits\n", encoding="utf-8")
            asset = media / "B00_opening" / "S001__0000-0004s__evidencia.mp4"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"fake-mp4")

            media_zip = root / "multimedia.zip"
            media_zip.write_bytes(b"zip")
            regression = root / "editorial-regression.json"
            regression.write_text(json.dumps({"structural_pass": True}), encoding="utf-8")
            cases = root / "evals" / "editorial" / "cases.json"
            cases.parent.mkdir(parents=True)
            cases.write_text(json.dumps({"cases": []}), encoding="utf-8")

            output = root / "site"
            index = build_site(
                episode_dir=episode,
                media_dir=media,
                media_zip=media_zip,
                regression_path=regression,
                cases_path=cases,
                output_dir=output,
                run_id="32541706631",
            )
            page = index.read_text(encoding="utf-8")

            self.assertIn('id="globalSearch"', page)
            self.assertIn("Buscar en guion, beats, fuentes, críticas, multimedia", page)
            self.assertIn("highlightScript", page)
            self.assertIn("data-search-item", page)
            self.assertIn('details class="diagnostic"', page)
            self.assertNotIn('details class="diagnostic" open', page)
            self.assertIn("Descargar multimedia ZIP", page)
            self.assertIn("<video", page)
            self.assertIn("TRACES benchmark", page)

            hero = page.split('<section class="hero">', 1)[1].split("</section>", 1)[0]
            self.assertNotIn('class="metrics"', hero)
            self.assertNotIn("Editorial</span>", hero)
            self.assertIn("Revisión humana", hero)
            self.assertIn("sin registro humano", hero)
            self.assertNotIn("Human review", hero)


if __name__ == "__main__":
    unittest.main()
