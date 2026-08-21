from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

from pipeline import run as pipeline_run


def plan_payload() -> dict:
    return {
        "topic_signature": "delegacion de criterio humano",
        "narrative_lens": "cognicion",
        "novelty_angle": "Cambia el foco desde capacidad a cierre de decisiones.",
        "historical_mirror": "Espejo histórico verificable.",
        "evidence_strategy": "Un caso prueba y otro complica.",
        "central_question": "¿Qué delegamos cuando dejamos que el sistema cierre el ciclo?",
        "thesis": "Parece un problema de verificación.",
        "hook": "El sistema dice que ya terminó.",
        "target_duration_minutes": 7.0,
        "narrative_arc": {
            "opening_belief": "Verificar parece suficiente.",
            "central_mystery": "¿Quién decide que algo terminó?",
            "concrete_scene": "Un agente resuelve un incidente solo.",
            "first_reveal": "Verificar también se automatiza.",
            "complication": "La supervisión humana puede volverse ritual.",
            "narrative_turn": "El problema se mueve hacia el criterio delegado.",
            "second_reveal": "Cerrar una tarea es una decisión.",
            "evolved_thesis": "Automatizamos el momento en que decidimos que una tarea merece considerarse terminada.",
            "recurring_motif": "Ya quedó.",
            "emotional_peak": "Alguien asume una decisión que nadie revisó realmente.",
            "final_payoff": "Ya quedó termina siendo una pregunta, no una confirmación.",
        },
        "stories": [{
            "selected_news_index": 1, "role": "anchor", "argument_role": "evidence",
            "estimated_minutes": 4, "narrative_function": "hacer tangible el problema",
        }],
        "final_synthesis": "La automatización desplaza el lugar del criterio.",
        "closing_question": "¿Qué no delegarías?",
    }


def marked_script() -> str:
    return (
        "<!--SECTION:opening-->" + " ".join(["inicio"] * 250) +
        " <!--SECTION:story:1-->" + " ".join(["desarrollo"] * 600) +
        " <!--SECTION:synthesis-->" + " ".join(["cierre"] * 200)
    )


def write_news(news: Path) -> None:
    (news / "2026-08-20.txt").write_text(
        "# Noticias\n\n## 1. Caso\nFecha: 2026-08-20\nFuente: Primaria\nEnlace: https://example.com/case\nCategoría: agentes\nResumen: Caso verificable\nPor qué importa: Impacto\n",
        encoding="utf-8",
    )


class E2EFailurePathTests(unittest.IsolatedAsyncioTestCase):
    async def test_voice_failure_stops_before_multimedia(self) -> None:
        steps: list[str] = []
        async def fake(agent, state, prompt, *, step, trace, iteration=None):
            steps.append(step)
            if step == "select_news":
                return {"selected_news": {"items": [{"news_id": "2026-08-20:1", "selection_reason": "relevante"}], "discarded_duplicates": [], "selection_notes": []}}
            if step == "plan_episode":
                return {"episode_plan": plan_payload()}
            if step == "write_script":
                return {"draft_script": marked_script()}
            if step == "editorial_judge":
                return {"review": {"score": 9.2, "approved": True, "factuality_risk": "low", "strengths": [], "problems": [], "improvements": []}}
            if step in {"seo_judge", "attention_judge"}:
                key = "seo_review" if step == "seo_judge" else "attention_review"
                return {key: {"score": 9.0, "approved": True, "strengths": [], "problems": [], "improvements": []}}
            if step == "voice_judge":
                return {"voice_review": {"score": 7.0, "approved": False, "voice_fidelity": 7, "intellectual_depth": 7, "human_relevance": 7, "analogy_quality": 7, "ai_smell_risk": "medium", "strengths": [], "problems": ["flat"], "improvements": []}}
            self.fail(f"Unexpected step {step}")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); news = root/"news"; scripts=root/"scripts"; media=root/"media"; history=root/"history"
            news.mkdir(); history.mkdir(); write_news(news)
            config = replace(pipeline_run.CONFIG, max_refinement_iterations=1)
            with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch.object(pipeline_run, "CONFIG", config), patch.object(pipeline_run, "run_agent", side_effect=fake):
                out = await pipeline_run.build(target_date=date(2026,8,21), news_dir=news, scripts_root=scripts, multimedia_root=media, history_scripts_root=history, max_media_downloads=0, download_multimedia=False)
            state = json.loads((out/"run_state.json").read_text())
            self.assertEqual(state["status"], "script_not_approved")
            self.assertNotIn("plan_multimedia", steps)

    async def test_exhausted_novelty_replans_stop_before_writer(self) -> None:
        steps: list[str] = []
        async def fake(agent, state, prompt, *, step, trace, iteration=None):
            steps.append(step)
            if step == "select_news":
                return {"selected_news": {"items": [{"news_id": "2026-08-20:1", "selection_reason": "relevante"}], "discarded_duplicates": [], "selection_notes": []}}
            if step in {"plan_episode", "replan_episode_novelty"}:
                return {"episode_plan": plan_payload()}
            self.fail(f"Unexpected step {step}")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); news = root/"news"; scripts=root/"scripts"; media=root/"media"; history=root/"history"
            news.mkdir(); history.mkdir(); write_news(news)
            old = history/"2026-08-20"; old.mkdir()
            (old/"reviews.json").write_text(json.dumps({"approved_for_multimedia": True}))
            (old/"episode_plan.json").write_text(json.dumps(plan_payload()))
            (old/"script.txt").write_text("ensayo previo")
            config = replace(pipeline_run.CONFIG, max_novelty_replans=1)
            duplicate = {"similarity": 0.95, "episode_date": "2026-08-20", "topic_signature": "same"}
            with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch.object(pipeline_run, "CONFIG", config), patch.object(pipeline_run, "run_agent", side_effect=fake), patch.object(pipeline_run, "nearest_essay_similarity", return_value=duplicate):
                out = await pipeline_run.build(target_date=date(2026,8,21), news_dir=news, scripts_root=scripts, multimedia_root=media, history_scripts_root=history, max_media_downloads=0, download_multimedia=False)
            state = json.loads((out/"run_state.json").read_text())
            self.assertEqual(state["status"], "no_novel_essay_angle")
            self.assertEqual(steps.count("replan_episode_novelty"), 1)
            self.assertNotIn("write_script", steps)


if __name__ == "__main__":
    unittest.main()
