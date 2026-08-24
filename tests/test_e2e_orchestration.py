from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from pipeline import run as pipeline_run


class OrchestrationE2ETests(unittest.IsolatedAsyncioTestCase):
    async def test_approved_episode_reaches_multimedia_without_external_calls(self) -> None:
        script = ("<!--SECTION:opening-->" + " ".join(["noticia"] * 250) + " <!--SECTION:beat:evidence-->" + " ".join(["noticia"] * 500) + " <!--SECTION:beat:turn-->" + " ".join(["noticia"] * 100) + " <!--SECTION:synthesis-->" + " ".join(["noticia"] * 200))

        async def fake_run_agent(agent, initial_state, prompt, *, step, trace, iteration=None):
            trace.append(
                {
                    "step": step,
                    "agent": getattr(agent, "name", step),
                    "iteration": iteration,
                    "attempt": 1,
                    "status": "success",
                    "elapsed_seconds": 0.0,
                    "usage": {},
                }
            )
            if step == "select_news":
                return {
                    "selected_news": {
                        "items": [
                            {
                                "news_id": "2026-08-20:1",
                                "selection_reason": "Evidencia útil para el ensayo",
                            }
                        ],
                        "discarded_duplicates": [],
                        "selection_notes": [],
                    }
                }
            if step in {"plan_episode", "replan_episode_novelty"}:
                return {
                    "episode_plan": {
                        "topic_signature": "delegacion de criterio y aprendizaje con IA",
                        "narrative_lens": "cognicion y educacion",
                        "novelty_angle": "Explora el cambio de hábitos de verificación, no solo capacidad del modelo.",
                        "historical_mirror": "La discusión histórica sobre herramientas que externalizan memoria.",
                        "evidence_strategy": "Usar el caso actual como evidencia de cómo cambia el criterio humano.",
                        "central_question": "¿Qué cambia cuando delegamos parte de nuestro razonamiento?",
                        "thesis": "La herramienta importa menos que la forma en que reorganiza nuestro criterio.",
                        "hook": "¿Y si una herramienta que nos ayuda a pensar también cambia cómo pensamos?",
                        "target_duration_minutes": 7.0,
                        "narrative_arc": {
                            "opening_belief": "Delegar criterio parece una comodidad inocente.",
                            "central_mystery": "¿Qué cambia en nosotros cuando dejamos de verificar?",
                            "concrete_scene": "Imagina una decisión cotidiana que aceptamos sin revisar porque la IA suena segura.",
                            "first_reveal": "La comodidad también modifica el hábito de comprobar.",
                            "complication": "Verificar todo manualmente tampoco escala ni garantiza buen juicio.",
                            "narrative_turn": "El problema deja de ser si la IA piensa y pasa a ser dónde ejercemos criterio.",
                            "second_reveal": "El diseño del proceso decide qué parte del juicio permanece humana.",
                            "evolved_thesis": "Automatizar no elimina el criterio: desplaza el lugar donde debemos ejercerlo conscientemente.",
                            "recurring_motif": "¿Ya quedó?",
                            "emotional_peak": "Una persona puede terminar asumiendo una decisión que nadie revisó realmente.",
                            "final_payoff": "La pregunta ya no es si la herramienta resolvió algo, sino qué significa realmente decir que ya quedó.",
                        },
                        "evidence": [
                            {
                                "evidence_id": "case",
                                "selected_news_index": 1,
                                "role": "anchor",
                                "argument_role": "evidence",
                                "narrative_function": "plantear el problema",
                                "analogy_goal": "comparar delegar criterio con usar una calculadora",
                                "skepticism_angle": "separar capacidad real de marketing",
                                "human_stakes": "aprendizaje y criterio"
                            }
                        ],
                        "claim_ledger": [
                            {
                                "evidence_id": "case",
                                "selected_news_index": 1,
                                "supported_facts": ["La noticia describe un caso verificable relacionado con IA."],
                                "allowed_interpretations": ["Puede usarse para discutir dónde ejercemos criterio."],
                                "hypotheses": [],
                                "uncertainties": ["El fixture no detalla resultados adicionales."],
                                "prohibited_claims": ["El caso demuestra que la IA elimina el criterio humano."],
                                "source_limitations": ["El fixture usa un resumen mínimo para pruebas."],
                            }
                        ],
                        "beats": [
                            {"beat_id": "evidence", "kind": "evidence", "purpose": "Volver concreta la tensión con evidencia actual.", "estimated_minutes": 3.0, "evidence_ids": ["case"]},
                            {"beat_id": "turn", "kind": "turn", "purpose": "Mover la pregunta desde capacidad hacia criterio.", "estimated_minutes": 2.5, "evidence_ids": []}
                        ],
                        "final_synthesis": "La pregunta no es solo qué puede hacer la IA, sino qué dejamos de hacer nosotros.",
                        "closing_question": "¿Qué parte de tu criterio no delegarías?",
                    }
                }
            if step == "write_script":
                return {"draft_script": script}
            if step == "editorial_judge":
                return {
                    "review": {
                        "score": 9.2,
                        "approved": True,
                        "factuality_risk": "low",
                        "strengths": [],
                        "problems": [],
                        "improvements": [],
                    }
                }
            if step == "seo_judge":
                return {
                    "seo_review": {
                        "score": 9.0,
                        "approved": True,
                        "strengths": [],
                        "problems": [],
                        "improvements": [],
                    }
                }
            if step == "attention_judge":
                return {
                    "attention_review": {
                        "score": 9.0,
                        "approved": True,
                        "strengths": [],
                        "problems": [],
                        "improvements": [],
                    }
                }
            if step == "voice_judge":
                return {
                    "voice_review": {
                        "score": 9.1,
                        "approved": True,
                        "voice_fidelity": 9.2,
                        "intellectual_depth": 9.0,
                        "human_relevance": 9.3,
                        "analogy_quality": 8.9,
                        "ai_smell_risk": "low",
                        "strengths": [],
                        "problems": [],
                        "improvements": [],
                    }
                }
            if step == "plan_multimedia":
                return {"multimedia_plan": {"segments": []}}
            self.fail(f"Unexpected orchestration step: {step}")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            news = root / "news"
            scripts = root / "scripts"
            media = root / "multimedia"
            history = root / "history"
            news.mkdir()
            history.mkdir()
            (news / "2026-08-20.txt").write_text(
                "# Noticias\n\n## 1. Noticia importante\nFecha: 2026-08-20\nFuente: Fuente primaria\nEnlace: https://example.com/story\nCategoría: educacion\nResumen: Resumen verificable\nPor qué importa: Impacto claro\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), patch.object(
                pipeline_run, "run_agent", side_effect=fake_run_agent
            ):
                result = await pipeline_run.build(
                    target_date=date(2026, 8, 21),
                    news_dir=news,
                    scripts_root=scripts,
                    multimedia_root=media,
                    history_scripts_root=history,
                    max_media_downloads=0,
                    download_multimedia=False,
                )

            self.assertEqual(result, scripts / "2026-08-21")
            state = json.loads((result / "run_state.json").read_text(encoding="utf-8"))
            reviews = json.loads((result / "reviews.json").read_text(encoding="utf-8"))
            trace = json.loads((result / "execution_trace.json").read_text(encoding="utf-8"))
            episode_plan = json.loads((result / "episode_plan.json").read_text(encoding="utf-8"))
            novelty = json.loads((result / "novelty_check.json").read_text(encoding="utf-8"))
            plan = json.loads((media / "2026-08-21" / "plan.json").read_text(encoding="utf-8"))

            self.assertEqual(state["status"], "approved")
            self.assertTrue(state["publishable"])
            self.assertTrue(reviews["gate"]["approved"])
            self.assertEqual(reviews["voice_humanity"]["ai_smell_risk"], "low")
            self.assertTrue(episode_plan["central_question"])
            self.assertTrue(episode_plan["topic_signature"])
            self.assertEqual(episode_plan["claim_ledger"][0]["evidence_id"], "case")
            self.assertTrue((result / "script_sections.json").exists())
            selected_payload = json.loads((result / "selected_news.json").read_text(encoding="utf-8"))
            self.assertEqual(selected_payload["items"][0]["source_locator"], "2026-08-20.txt#item-1")
            self.assertEqual(selected_payload["items"][0]["url"], "https://example.com/story")
            self.assertEqual(novelty["previous_essay_count"], 0)
            self.assertFalse(novelty["attempts"][-1]["duplicate"])
            self.assertGreaterEqual(plan["timeline_duration_seconds"], 420)
            self.assertEqual(plan["segments"][0]["start_seconds"], 0)
            self.assertEqual(plan["segments"][0]["end_seconds"], 3)
            self.assertGreaterEqual(len(trace["agent_calls"]), 8)
            self.assertEqual(trace["refinement_iterations"][0]["approved"], True)


if __name__ == "__main__":
    unittest.main()
