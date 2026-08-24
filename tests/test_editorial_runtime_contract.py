from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.agent import EpisodePlan, editorial_director_agent, writer_agent
from app.refiners import factual_refiner_agent, secondary_refiner_agent, voice_refiner_agent
from pipeline.run import _select_refinement_phase


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
            "evidence_id": "case", "selected_news_index": 1, "role": "anchor", "argument_role": "evidence",
            "narrative_function": "volver concreto el misterio",
        }],
        "claim_ledger": [{
            "evidence_id": "case",
            "selected_news_index": 1,
            "supported_facts": ["El caso describe una automatización que cierra una tarea."],
            "allowed_interpretations": ["Puede leerse como un cambio en dónde ejercemos criterio."],
            "hypotheses": ["Podría reducir la revisión humana si se adopta sin controles."],
            "uncertainties": ["No sabemos cómo se valida el cierre en producción."],
            "prohibited_claims": ["La automatización elimina la supervisión humana."],
            "source_limitations": ["El resumen no describe métricas de validación."],
        }],
        "beats": [
            {"beat_id": "reveal", "kind": "reveal", "purpose": "La evidencia cambia la creencia inicial.", "estimated_minutes": 3, "evidence_ids": ["case"]},
            {"beat_id": "turn", "kind": "turn", "purpose": "La pregunta se mueve hacia el criterio delegado.", "estimated_minutes": 3, "evidence_ids": []}
        ],
        "final_synthesis": "La automatización mueve el lugar donde ejercemos criterio.",
        "closing_question": "¿Qué significa para ti que algo ya quedó?",
    }


def gate_checks(*, factual: bool, voice: bool, seo: bool = True, attention: bool = True) -> dict:
    return {
        "checks": {
            "editorial_approved": factual,
            "editorial_score_ok": factual,
            "factuality_low": factual,
            "voice_approved": voice,
            "voice_score_ok": voice,
            "ai_smell_low": voice,
            "seo_approved": seo,
            "seo_score_ok": seo,
            "attention_approved": attention,
            "attention_score_ok": attention,
            "script_present": True,
            "duration_ok": True,
        }
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
        self.assertEqual(plan.beats[0].evidence_ids, ["case"])
        self.assertEqual(plan.beats[1].evidence_ids, [])
        self.assertFalse(hasattr(plan, "stories"))

    def test_episode_plan_rejects_non_evolving_thesis(self) -> None:
        plan = valid_plan()
        plan["narrative_arc"]["evolved_thesis"] = plan["thesis"]
        with self.assertRaises(ValidationError):
            EpisodePlan.model_validate(plan)

    def test_claim_ledger_is_required_and_matches_evidence(self) -> None:
        plan = EpisodePlan.model_validate(valid_plan())
        self.assertEqual(plan.claim_ledger[0].evidence_id, "case")
        self.assertTrue(plan.claim_ledger[0].supported_facts)

        missing = valid_plan()
        missing.pop("claim_ledger")
        with self.assertRaises(ValidationError):
            EpisodePlan.model_validate(missing)

        mismatch = valid_plan()
        mismatch["claim_ledger"][0]["evidence_id"] = "other"
        with self.assertRaises(ValidationError):
            EpisodePlan.model_validate(mismatch)

    def test_factual_and_voice_refiners_are_separate_agents_with_isolated_contexts(self) -> None:
        factual = factual_refiner_agent.instruction.lower()
        voice = voice_refiner_agent.instruction.lower()
        secondary = secondary_refiner_agent.instruction.lower()

        self.assertEqual(factual_refiner_agent.name, "factual_script_refiner")
        self.assertEqual(voice_refiner_agent.name, "voice_script_refiner")
        self.assertNotEqual(factual_refiner_agent.name, voice_refiner_agent.name)

        self.assertIn("your only job is factual repair", factual)
        self.assertIn("do not optimize voice", factual)
        self.assertNotIn("{voice_review}", factual)
        self.assertNotIn("{seo_review}", factual)
        self.assertNotIn("{attention_review}", factual)

        self.assertIn("the semantic claim set is frozen", voice)
        self.assertIn("do not receive news_text", voice)
        self.assertNotIn("{news_text}", voice)
        self.assertNotIn("{selected_news}", voice)
        self.assertNotIn("{review}", voice)
        self.assertNotIn("{seo_review}", voice)
        self.assertNotIn("{attention_review}", voice)

        self.assertIn("factuality and voice already pass", secondary)

    def test_refinement_routing_is_deterministic_and_factual_first(self) -> None:
        self.assertEqual(
            _select_refinement_phase(gate_checks(factual=False, voice=False)), "factual"
        )
        self.assertEqual(
            _select_refinement_phase(gate_checks(factual=False, voice=True)), "factual"
        )
        self.assertEqual(
            _select_refinement_phase(gate_checks(factual=True, voice=False)), "voice"
        )
        self.assertEqual(
            _select_refinement_phase(
                gate_checks(factual=True, voice=True, seo=False, attention=True)
            ),
            "secondary",
        )


if __name__ == "__main__":
    unittest.main()
