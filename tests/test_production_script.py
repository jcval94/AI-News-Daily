from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.production_script import (
    build_production_payload,
    create_production_script,
    format_time,
    render_markdown,
)


class ProductionScriptTests(unittest.TestCase):
    def test_build_production_payload_adds_sections_cta_and_media(self) -> None:
        script = " ".join(
            [
                "No sé si te pasa algo parecido, pero delegar una decisión a una IA puede sentirse cómodo.",
                "La comodidad no siempre significa que entendamos qué ocurrió.",
                "Por eso conviene mirar qué pasa cuando estos sistemas actúan fuera de una demostración.",
                "Un caso reciente permite volver la pregunta mucho más concreta.",
                "La evidencia muestra una mejora, pero también deja límites que no conviene borrar.",
                "Otro ejemplo complica la lectura porque el costo de equivocarse cambia por completo.",
                "La idea importante no es desconfiar de todo, sino aprender qué señales merecen nuestra atención.",
                "Después de revisar los casos, la tesis inicial necesita un matiz.",
                "La pregunta final es cuánto criterio queremos conservar cuando automatizamos una decisión.",
            ]
            * 12
        )
        episode_plan = {
            "hook": "La comodidad de delegar decisiones puede ocultar cuánto entendemos.",
            "historical_mirror": "Las calculadoras cambiaron qué operaciones hacemos mentalmente.",
            "final_synthesis": "Automatizar no elimina la necesidad de criterio; cambia dónde se ejerce.",
            "closing_question": "¿Qué parte de tu criterio no delegarías?",
            "beats": [
                {
                    "beat_id": "first-reveal",
                    "kind": "reveal",
                    "estimated_minutes": 3.0,
                    "purpose": "Mostrar cuándo la automatización sí produce una ventaja verificable.",
                    "evidence_news_indices": [1],
                },
                {
                    "beat_id": "complication",
                    "kind": "complication",
                    "estimated_minutes": 2.0,
                    "purpose": "Complicar la tesis con un caso donde equivocarse cuesta más.",
                    "evidence_news_indices": [2],
                },
            ],
        }
        selected_news = {
            "items": [
                {"title": "Caso A"},
                {"title": "Caso B"},
            ]
        }
        media_plan = {
            "segments": [
                {
                    "slot_number": 1,
                    "start_seconds": 10,
                    "end_seconds": 14,
                    "mode": "media",
                    "visual_query": "person choosing between two options",
                    "on_screen_text": "¿Qué delegamos?",
                    "reason": "Anclar la tensión humana.",
                },
                {
                    "slot_number": 2,
                    "start_seconds": 95,
                    "end_seconds": 99,
                    "mode": "presenter",
                    "visual_query": "",
                    "on_screen_text": "",
                    "reason": "",
                },
            ]
        }

        payload = build_production_payload(
            target_date="2026-08-21",
            script=script,
            episode_plan=episode_plan,
            selected_news=selected_news,
            media_plan=media_plan,
            words_per_second=2.5,
        )

        self.assertTrue(payload["cta_injected"])
        self.assertEqual(payload["media_insert_count"], 1)
        self.assertEqual(payload["sections"][0]["kind"], "opening")
        self.assertEqual(payload["sections"][-1]["kind"], "cta")
        self.assertGreaterEqual(len(payload["sections"]), 5)
        self.assertIn("suscríbete", payload["cta_text"].lower())
        self.assertLess(
            payload["sections"][0]["start_seconds"],
            payload["sections"][-1]["end_seconds"],
        )
        self.assertEqual(
            payload["production_duration_seconds"],
            payload["sections"][-1]["end_seconds"],
        )

        markdown = render_markdown(payload)
        self.assertIn("## Capítulos / timecodes", markdown)
        self.assertIn("### Narración", markdown)
        self.assertIn("### Multimedia / B-roll", markdown)
        self.assertIn("CTA — conversación y suscripción", markdown)
        self.assertIn("Búsqueda visual", markdown)

    def test_existing_cta_is_detected_not_duplicated(self) -> None:
        script = (
            "Pensemos primero en la tensión humana. "
            "Después de revisar la evidencia, la pregunta sigue abierta. "
            "Si esta charla te sirvió, suscríbete y te leo en los comentarios."
        )
        payload = build_production_payload(
            target_date="2026-08-21",
            script=script,
            episode_plan={"closing_question": "¿Qué harías tú?", "stories": []},
            selected_news={},
            media_plan={},
            words_per_second=2.5,
        )
        self.assertFalse(payload["cta_injected"])
        self.assertEqual(payload["cta_text"].lower().count("suscríbete"), 1)
        self.assertEqual(payload["sections"][-1]["kind"], "cta")

    def test_create_production_script_skips_cleanly_without_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = create_production_script(
                target_date="2026-08-21",
                scripts_root=root / "scripts",
                multimedia_root=root / "multimedia",
                words_per_second=2.5,
            )
            self.assertIsNone(result)

    def test_create_production_script_writes_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts_dir = root / "scripts" / "2026-08-21"
            media_dir = root / "multimedia" / "2026-08-21"
            scripts_dir.mkdir(parents=True)
            media_dir.mkdir(parents=True)
            (scripts_dir / "script.txt").write_text(
                "Una idea merece contexto. " * 200,
                encoding="utf-8",
            )
            (scripts_dir / "episode_plan.json").write_text(
                json.dumps(
                    {
                        "hook": "Una tensión reconocible.",
                        "final_synthesis": "Una síntesis con matiz.",
                        "closing_question": "¿Qué opinas?",
                        "stories": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (scripts_dir / "selected_news.json").write_text("{}", encoding="utf-8")
            (media_dir / "plan.json").write_text("{}", encoding="utf-8")

            result = create_production_script(
                target_date="2026-08-21",
                scripts_root=root / "scripts",
                multimedia_root=root / "multimedia",
                words_per_second=2.5,
            )
            self.assertIsNotNone(result)
            md_path, json_path = result
            self.assertTrue(md_path.exists())
            self.assertTrue(json_path.exists())
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["episode_date"], "2026-08-21")
            self.assertIn("00:00", md_path.read_text(encoding="utf-8"))

    def test_format_time(self) -> None:
        self.assertEqual(format_time(0), "00:00")
        self.assertEqual(format_time(65), "01:05")
        self.assertEqual(format_time(3661), "01:01:01")


    def test_writer_alignment_overrides_proportional_allocation(self) -> None:
        from pipeline.production_script import build_production_payload

        script = "Inicio corto. Caso muy concreto con varias palabras. Cierre final."
        episode_plan = {
            "hook": "hook",
            "historical_mirror": "",
            "beats": [{"beat_id": "case", "kind": "evidence", "estimated_minutes": 4, "purpose": "Caso real", "evidence_news_indices": [1]}],
            "final_synthesis": "síntesis",
            "closing_question": "¿Qué cambia?",
        }
        selected = {"items": [{"title": "Fuente exacta"}]}
        alignment = {"sections": [
            {"section_key": "opening", "spoken_text": "Inicio corto."},
            {"section_key": "beat:case", "spoken_text": "Caso muy concreto con varias palabras."},
            {"section_key": "synthesis", "spoken_text": "Cierre final."},
        ]}
        payload = build_production_payload(
            target_date="2026-08-21", script=script, episode_plan=episode_plan, selected_news=selected,
            media_plan={}, words_per_second=2.5, script_alignment=alignment
        )
        self.assertEqual(payload["alignment_mode"], "writer_markers")
        self.assertEqual(payload["sections"][1]["spoken_text"], "Caso muy concreto con varias palabras.")
        self.assertEqual(payload["sections"][1]["source_evidence"], "Fuente exacta")


if __name__ == "__main__":
    unittest.main()
