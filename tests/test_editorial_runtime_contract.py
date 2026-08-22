from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.agent import EpisodePlan, editorial_director_agent, writer_agent


def valid_plan() -> dict:
    return {
        "topic_signature": "criterio humano bajo automatizacion",
        "narrative_lens": "cognicion",
        "novelty_angle": "Investiga el cierre de tareas, no la capacidad bruta.",
        "historical_mirror": "Una herramienta histórica cambia qué consideramos saber.",
        "evidence_strategy": "Casos actuales complican una creencia inicial.",
        "central_question": "¿Cuándo deja de ser ayuda y empieza a ser delegación?",
        "thesis": "Al principio parece que el problema es verificar a la máquina.",
        "hook": "Una marca verde dice que todo terminó. ¿Pero quién decidió eso?",
        "target_duration_minutes": 10,
        "narrative_arc": {
            "opening_belief": "Verificar mejor parece suficiente.",
            "central_mystery": "¿Qué significa realmente terminar una tarea?",
            "concrete_scene": "Un agente cierra un incidente de madrugada sin intervención.",
            "first_reveal": "La verificación también puede automatizarse.",
            "complication": "El humano puede terminar confiando en el proceso de verificación.",
            "narrative_turn": "El problema pasa de errores de IA a criterio delegado.",
            "second_reveal": "La decisión de dar algo por terminado es también trabajo cognitivo.",
            "evolved_thesis": "Automatizamos no solo tareas, sino el momento en que decidimos que merecen considerarse terminadas.",
            "recurring_motif": "Ya quedó.",
            "emotional_peak": "Una persona asume una decisión que nadie revisó conscientemente.",
            "final_payoff": "Al final, ya quedó deja de ser una confirmación y se vuelve una pregunta.",
        },
        "evidence": [{
            "selected_news_index": 1, "role": "anchor", "argument_role": "evidence",
            "narrative_function": "volver concreto el misterio",
        }],
        "beats": [
            {"beat_id": "reveal", "kind": "reveal", "purpose": "La evidencia cambia la creencia inicial.", "estimated_minutes": 3, "evidence_news_indices": [1]},
            {"beat_id": "turn", "kind": "turn", "purpose": "La pregunta se mueve hacia el criterio delegado.", "estimated_minutes": 3, "evidence_news_indices": []}
        ],
        "final_synthesis": "La automatización mueve el lugar donde ejercemos criterio.",
        "closing_question": "¿Qué significa para ti que algo ya quedó?",
    }


class EditorialRuntimeContractTests(unittest.TestCase):
    def test_director_and_writer_runtime_prompts_contain_full_dramaturgy(self) -> None:
        director = editorial_director_agent.instruction.lower()
        writer = writer_agent.instruction.lower()
        fields = (
            "opening_belief", "central_mystery", "concrete_scene", "first_reveal",
            "complication", "narrative_turn", "second_reveal", "evolved_thesis",
            "recurring_motif", "emotional_peak", "final_payoff",
        )
        for field in fields:
            self.assertIn(field, director)
            self.assertIn(field, writer)

    def test_episode_plan_requires_complete_narrative_arc(self) -> None:
        plan = valid_plan()
        del plan["narrative_arc"]["narrative_turn"]
        with self.assertRaises(ValidationError):
            EpisodePlan.model_validate(plan)

    def test_episode_plan_beats_are_not_one_news_per_section_contract(self) -> None:
        plan = EpisodePlan.model_validate(valid_plan())
        self.assertEqual(plan.beats[0].evidence_news_indices, [1])
        self.assertEqual(plan.beats[1].evidence_news_indices, [])
        self.assertFalse(hasattr(plan, "stories"))

    def test_episode_plan_rejects_non_evolving_thesis(self) -> None:
        plan = valid_plan()
        plan["narrative_arc"]["evolved_thesis"] = plan["thesis"]
        with self.assertRaises(ValidationError):
            EpisodePlan.model_validate(plan)


if __name__ == "__main__":
    unittest.main()
