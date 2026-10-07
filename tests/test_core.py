from __future__ import annotations

import unittest
from datetime import date

from pipeline.core import (
    PipelineConfig,
    assess_episode_novelty,
    build_timeline_slots,
    duration_within_target,
    evaluate_script_gate,
    expected_news_dates,
    is_retryable_exception,
    nearest_essay_similarity,
    timeline_duration_seconds,
    topic_similarity,
)


class DummyRateLimitError(Exception):
    status_code = 429


class CoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = PipelineConfig().validated()

    def test_tuesday_window(self) -> None:
        self.assertEqual(
            [d.isoformat() for d in expected_news_dates(date(2026, 8, 25))],
            ["2026-08-21", "2026-08-22", "2026-08-23", "2026-08-24"],
        )

    def test_friday_window(self) -> None:
        self.assertEqual(
            [d.isoformat() for d in expected_news_dates(date(2026, 8, 21))],
            ["2026-08-18", "2026-08-19", "2026-08-20"],
        )

    def test_duration_bounds(self) -> None:
        self.assertTrue(duration_within_target("x " * 1050, self.config))
        self.assertTrue(duration_within_target("x " * 3000, self.config))
        self.assertFalse(duration_within_target("x " * 1000, self.config))
        self.assertFalse(duration_within_target("x " * 3100, self.config))

    def test_timeline_never_truncates_narration(self) -> None:
        script = "x " * 3000
        duration = timeline_duration_seconds(script, self.config)
        self.assertGreaterEqual(duration, self.config.target_max_seconds)
        slots = build_timeline_slots(duration, self.config)
        self.assertEqual(
            [(s["start_seconds"], s["end_seconds"]) for s in slots[:5]],
            [(0, 3), (3, 6), (6, 9), (9, 12), (12, 15)],
        )
        self.assertEqual(
            (slots[5]["start_seconds"], slots[5]["end_seconds"]), (15, 19)
        )
        self.assertEqual(slots[-1]["end_seconds"], duration)

    def test_gate_is_deterministic(self) -> None:
        script = "x " * 1050
        editorial = {"approved": True, "score": 9.0, "factuality_risk": "low"}
        seo = {"approved": True, "score": 9.0}
        attention = {"approved": True, "score": 9.0}
        voice = {"approved": True, "score": 9.1, "ai_smell_risk": "low"}
        self.assertTrue(
            evaluate_script_gate(
                script, editorial, seo, attention, voice, self.config
            )["approved"]
        )
        voice["ai_smell_risk"] = "medium"
        self.assertFalse(
            evaluate_script_gate(
                script, editorial, seo, attention, voice, self.config
            )["approved"]
        )

    def test_retry_classification(self) -> None:
        self.assertTrue(is_retryable_exception(DummyRateLimitError("rate")))
        self.assertFalse(is_retryable_exception(ValueError("bad input")))

    def test_topic_similarity_detects_rephrased_same_angle(self) -> None:
        left = "dependencia cognitiva: que dejamos de pensar cuando delegamos razonamiento a la IA"
        right = "delegar razonamiento a inteligencia artificial y perder criterio o independencia cognitiva"
        unrelated = "robots científicos para diseñar nuevos catalizadores en laboratorios físicos"
        self.assertGreater(topic_similarity(left, right), topic_similarity(left, unrelated))
        self.assertGreater(topic_similarity(left, right), 0.35)

    def test_topic_similarity_catches_auditability_theme_with_different_wording(self) -> None:
        previous = (
            "La IA ya toca cosas reales. El reto es pasar de demos a sistemas que operan con "
            "herramientas, gobernanza y resultados que podamos comprobar antes de confiar en ellos."
        )
        candidate = (
            "Agencia auditable: responsabilidad institucional, evidencia, trazabilidad y verificación "
            "de acciones realizadas por agentes autónomos."
        )
        unrelated = (
            "Qué pasa con el aprendizaje y la memoria cuando estudiantes delegan el razonamiento "
            "cotidiano a tutores de inteligencia artificial."
        )
        similar_score = topic_similarity(previous, candidate)
        unrelated_score = topic_similarity(previous, unrelated)
        self.assertGreaterEqual(similar_score, self.config.essay_duplicate_threshold)
        self.assertGreater(similar_score, unrelated_score)


    def test_topic_similarity_does_not_block_same_broad_work_concept(self) -> None:
        left = "El futuro del trabajo cambia cuando asistentes de IA automatizan tareas administrativas."
        right = "Los ilustradores discuten derechos de autor y estilos generados por IA en su trabajo creativo."
        self.assertLess(topic_similarity(left, right), self.config.essay_duplicate_threshold)

    def test_topic_similarity_does_not_block_same_broad_trust_word(self) -> None:
        left = "¿Podemos confiar en un agente que modifica producción sin supervisión?"
        right = "¿Qué significa la confianza emocional tras meses conversando con un compañero de IA?"
        self.assertLess(topic_similarity(left, right), self.config.essay_duplicate_threshold)

    def test_multidimensional_novelty_allows_october_signal_episode_despite_broad_concepts(self) -> None:
        candidate = {
            "topic_signature": "Señales probabilísticas y evaluación imperfecta: cómo la gente y las instituciones convierten incertidumbre en decisión",
            "central_question": "Cuando una institución recibe una señal útil pero imperfecta, ¿qué impide que esa señal se convierta en prueba suficiente y que el error se asigne a quienes menos pueden impugnar?",
            "thesis": "Una señal probabilística puede ser útil, pero se vuelve peligrosa cuando un proceso de decisión la trata como evidencia concluyente y premia la señal en lugar del estado que representa.",
            "narrative_lens": "confianza, evidencias y gobernanza de la incertidumbre",
            "primary_memory_id": "hanoi-rat-tail-bounty-gaming",
            "narrative_arc": {
                "narrative_turn": "La clave no es sólo el error del detector, sino el acoplamiento entre una señal y el procedimiento institucional que la convierte en decisión.",
                "evolved_thesis": "La meta debe ser preservar la incertidumbre como un objeto de decisión visible, contextual e impugnable, no esconderla detrás de una etiqueta.",
            },
            "evidence": [
                {"selected_news_index": 1},
                {"selected_news_index": 2},
            ],
        }
        selected = [
            {"news_id": "oct-provenance", "url": "https://example.com/provenance"},
            {"news_id": "oct-context", "url": "https://example.com/context"},
        ]
        previous = [{
            "episode_date": "2026-09-04",
            "topic_signature": "La diferencia entre usar una IA para rendir mejor y conservar la capacidad humana de saber cuándo confiar, intervenir o actuar sin ella",
            "central_question": "Cuando una herramienta puede hacer cada vez más trabajo mental por nosotros, ¿qué debemos seguir siendo capaces de hacer sin ella para que nuestra confianza no se convierta en dependencia ciega?",
            "thesis": "La habilidad humana más importante junto a la IA quizá no sea ejecutar cada tarea manualmente, sino conservar suficiente comprensión para reconocer los límites de la herramienta, verificar sus resultados y recuperar criterio cuando la asistencia desaparece.",
            "narrative_lens": "cognición, aprendizaje y responsabilidad",
            "mechanism": (
                "El problema es qué tipo de relación cognitiva diseña la IA: una que sustituye el juicio "
                "o una que enseña al usuario a detectar sorpresa, incertidumbre y límites. "
                "La asistencia debería preservar calibración humana y la capacidad de juzgar la ayuda."
            ),
            "primary_memory_id": "phaedrus-writing-memory",
            "evidence_keys": ["url:https://example.com/learning"],
        }]

        legacy_candidate = " ".join(
            str(candidate.get(key, "") or "")
            for key in ("topic_signature", "central_question", "thesis", "narrative_lens")
        )
        legacy = nearest_essay_similarity(legacy_candidate, previous)
        self.assertIsNotNone(legacy)
        assert legacy is not None
        self.assertGreaterEqual(
            legacy["similarity"], self.config.essay_duplicate_threshold
        )

        assessment = assess_episode_novelty(
            candidate,
            selected,
            previous,
            self.config.essay_duplicate_threshold,
        )
        self.assertFalse(assessment["duplicate"])
        nearest = assessment["nearest_previous_essay"]
        self.assertIsNotNone(nearest)
        assert nearest is not None
        self.assertLess(
            nearest["dimensions"]["mechanism"],
            assessment["dimension_thresholds"]["core"],
        )
        self.assertEqual(nearest["decision_reasons"], [])

    def test_multidimensional_novelty_blocks_same_agent_delegation_core(self) -> None:
        candidate = {
            "topic_signature": "Responsabilidad cuando agentes persistentes ejecutan trabajo delegado",
            "central_question": "Si un agente puede vigilar, decidir y ejecutar durante horas sin supervisión continua, ¿quién responde cuando una acción autónoma cruza un límite?",
            "thesis": "El problema central no es sólo qué permisos dar a los agentes, sino cómo hacer la delegación visible, acotada, reversible y atribuible a una organización responsable.",
            "narrative_lens": "instituciones, responsabilidad y trabajo",
            "primary_memory_id": "electrification-organizational-redesign",
            "narrative_arc": {
                "narrative_turn": "Cuando los agentes encadenan acciones, la organización necesita identidades separadas, límites de alcance, registros interpretables y escalamiento.",
                "evolved_thesis": "La cuestión no es automatizar más tareas, sino construir una institución de delegación que conserve responsabilidad humana.",
            },
            "evidence": [{"selected_news_index": 1}],
        }
        selected = [
            {
                "news_id": "new-agent-case",
                "url": "https://example.com/new-agent-case",
            }
        ]
        previous = [{
            "episode_date": "2026-09-25",
            "topic_signature": "La responsabilidad organizacional cuando agentes de IA ejecutan trabajo continuo y toman acciones delegadas",
            "central_question": "Cuando una organización delega trabajo a agentes que pueden vigilar, decidir y ejecutar durante horas sin una persona presente, ¿dónde debe vivir la responsabilidad cuando algo sale mal?",
            "thesis": "El reto principal de los agentes no es sólo darles permisos seguros, sino convertir la delegación en algo visible, limitado y reversible.",
            "narrative_lens": "instituciones, responsabilidad y trabajo",
            "mechanism": (
                "Gobernar agentes requiere identidades separadas, límites de alcance, registros interpretables, "
                "puntos de escalamiento y capacidad de detener, explicar y reparar una decisión. "
                "Hace falta una institución de delegación que conserve responsabilidad humana."
            ),
            "primary_memory_id": "electrification-organizational-redesign",
            "evidence_keys": ["url:https://example.com/old-agent-case"],
        }]

        assessment = assess_episode_novelty(
            candidate,
            selected,
            previous,
            self.config.essay_duplicate_threshold,
        )
        self.assertTrue(assessment["duplicate"])
        nearest = assessment["nearest_previous_essay"]
        self.assertIsNotNone(nearest)
        assert nearest is not None
        self.assertTrue(nearest["duplicate"])
        self.assertIn(
            "same_mechanism_and_argument",
            nearest["decision_reasons"],
        )

    def test_nearest_essay_similarity_ignores_script_excerpt_contamination(self) -> None:
        candidate = (
            "responsabilidad institucional agentes persistentes permisos revocacion "
            "auditoria y delegacion continua"
        )
        previous = [{
            "episode_date": "2026-09-04",
            "topic_signature": "dependencia cognitiva y criterio humano",
            "central_question": "¿Qué debemos seguir sabiendo hacer sin una IA?",
            "thesis": "Conservar comprensión permite detectar límites y recuperar criterio.",
            "narrative_lens": "cognicion aprendizaje",
            "script_excerpt": candidate * 8,
        }]
        nearest = nearest_essay_similarity(candidate, previous)
        self.assertIsNotNone(nearest)
        assert nearest is not None
        self.assertLess(nearest["similarity"], self.config.essay_duplicate_threshold)

    def test_nearest_essay_similarity_returns_best_match(self) -> None:
        previous = [
            {
                "episode_date": "2026-08-01",
                "topic_signature": "dependencia cognitiva y delegación de razonamiento",
                "central_question": "¿Qué dejamos de pensar cuando una IA piensa por nosotros?",
                "thesis": "La comodidad puede cambiar hábitos cognitivos.",
                "narrative_lens": "cognicion",
            },
            {
                "episode_date": "2026-08-08",
                "topic_signature": "IA científica en laboratorios físicos",
                "central_question": "¿Puede una IA proponer experimentos útiles?",
                "thesis": "La evidencia física cambia cómo medimos capacidad.",
                "narrative_lens": "ciencia",
            },
        ]
        nearest = nearest_essay_similarity(
            "dependencia cognitiva delegar razonamiento perder criterio", previous
        )
        self.assertIsNotNone(nearest)
        self.assertEqual(nearest["episode_date"], "2026-08-01")


if __name__ == "__main__":
    unittest.main()
