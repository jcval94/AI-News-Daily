from __future__ import annotations

import unittest
from datetime import date

from pipeline.core import (
    PipelineConfig,
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
