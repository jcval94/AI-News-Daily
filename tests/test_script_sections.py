from __future__ import annotations

import unittest

from pipeline.script_sections import SectionAlignmentError, parse_sectioned_script


PLAN = {
    "opening_memory_id": "memory-case",
    "beats": [
        {"beat_id": "first-reveal", "kind": "reveal", "evidence_ids": ["case-a", "case-b"]},
        {"beat_id": "turn", "kind": "turn", "evidence_ids": []},
    ]
}


class ScriptSectionTests(unittest.TestCase):
    def test_markers_follow_idea_beats_not_news_items(self) -> None:
        marked = (
            "<!--SECTION:opening--><!--MEMORY:memory-case-->Inicio intrigante. "
            "<!--SECTION:beat:first-reveal-->Dos casos se comparan dentro del mismo argumento. "
            "<!--SECTION:beat:turn-->Aquí cambia la pregunta sin introducir otra noticia. "
            "<!--SECTION:synthesis-->Cierre que transforma el inicio."
        )
        clean, payload = parse_sectioned_script(marked, PLAN)
        self.assertNotIn("SECTION", clean)
        self.assertNotIn("MEMORY", clean)
        self.assertEqual(payload["schema_version"], 4)
        self.assertEqual(payload["narrative_memory"]["primary_memory_id"], "memory-case")
        self.assertEqual(payload["narrative_memory"]["opening_memory_id"], "memory-case")
        self.assertEqual(payload["narrative_memory"]["placement"], "opening")
        self.assertEqual(payload["narrative_memory"]["section_key"], "opening")
        self.assertEqual(
            [item["section_key"] for item in payload["sections"]],
            ["opening", "beat:first-reveal", "beat:turn", "synthesis"],
        )
        self.assertEqual(payload["sections"][1]["evidence_ids"], ["case-a", "case-b"])
        self.assertEqual(payload["sections"][2]["evidence_ids"], [])

    def test_narrative_turn_memory_marker_is_allowed_inside_turn_beat(self) -> None:
        plan = {
            "primary_memory_id": "memory-case",
            "narrative_parallels": [
                {
                    "memory_id": "memory-case",
                    "placement": "narrative_turn",
                    "role": "historical_mirror",
                    "purpose": "Reencuadrar el problema después de volverlo concreto.",
                    "limits": "No asumir causalidad idéntica.",
                }
            ],
            "beats": [
                {"beat_id": "evidence", "kind": "evidence", "evidence_ids": ["case-a"]},
                {"beat_id": "turn", "kind": "turn", "evidence_ids": []},
            ],
        }
        marked = (
            "<!--SECTION:opening-->Tensión humana concreta. "
            "<!--SECTION:beat:evidence-->Aquí entra evidencia actual. "
            "<!--SECTION:beat:turn--><!--MEMORY:memory-case-->La historia cambia cómo entendemos el caso. "
            "<!--SECTION:synthesis-->Cierre."
        )
        clean, payload = parse_sectioned_script(marked, plan)
        self.assertNotIn("MEMORY", clean)
        self.assertEqual(payload["narrative_memory"]["placement"], "narrative_turn")
        self.assertEqual(payload["narrative_memory"]["section_key"], "beat:turn")
        self.assertEqual(payload["first_evidence_start_word"], 3)

    def test_narrative_turn_memory_marker_in_opening_is_rejected(self) -> None:
        plan = {
            "primary_memory_id": "memory-case",
            "narrative_parallels": [
                {
                    "memory_id": "memory-case",
                    "placement": "narrative_turn",
                    "role": "historical_mirror",
                    "purpose": "Reencuadrar.",
                    "limits": "No equivalencia causal.",
                }
            ],
            "beats": [
                {"beat_id": "turn", "kind": "turn", "evidence_ids": []},
            ],
        }
        marked = (
            "<!--SECTION:opening--><!--MEMORY:memory-case-->Historia demasiado pronto. "
            "<!--SECTION:beat:turn-->Giro. "
            "<!--SECTION:synthesis-->Cierre."
        )
        with self.assertRaises(SectionAlignmentError):
            parse_sectioned_script(marked, plan)

    def test_trailing_marker_only_debris_is_ignored(self) -> None:
        marked = (
            "<!--SECTION:opening--><!--MEMORY:memory-case-->Inicio. "
            "<!--SECTION:beat:first-reveal-->Revelación. "
            "<!--SECTION:beat:turn-->Giro. "
            "<!--SECTION:synthesis-->Cierre. "
            "<!--SECTION:beat:first-reveal-->"
        )
        clean, payload = parse_sectioned_script(marked, PLAN)
        self.assertEqual(len(payload["sections"]), 4)
        self.assertTrue(clean.endswith("Cierre."))

    def test_trailing_duplicate_with_spoken_text_is_rejected(self) -> None:
        marked = (
            "<!--SECTION:opening--><!--MEMORY:memory-case-->Inicio. "
            "<!--SECTION:beat:first-reveal-->Revelación. "
            "<!--SECTION:beat:turn-->Giro. "
            "<!--SECTION:synthesis-->Cierre. "
            "<!--SECTION:beat:first-reveal-->Texto que no pertenece al cierre."
        )
        with self.assertRaises(SectionAlignmentError):
            parse_sectioned_script(marked, PLAN)

    def test_missing_memory_marker_is_rejected(self) -> None:
        marked = (
            "<!--SECTION:opening-->Inicio. "
            "<!--SECTION:beat:first-reveal-->Revelación. "
            "<!--SECTION:beat:turn-->Giro. "
            "<!--SECTION:synthesis-->Cierre."
        )
        with self.assertRaises(SectionAlignmentError):
            parse_sectioned_script(marked, PLAN)

    def test_wrong_memory_id_is_rejected(self) -> None:
        marked = (
            "<!--SECTION:opening--><!--MEMORY:other-case-->Inicio. "
            "<!--SECTION:beat:first-reveal-->Revelación. "
            "<!--SECTION:beat:turn-->Giro. "
            "<!--SECTION:synthesis-->Cierre."
        )
        with self.assertRaises(SectionAlignmentError):
            parse_sectioned_script(marked, PLAN)

    def test_memory_marker_too_late_is_rejected(self) -> None:
        prefix = " ".join(["palabra"] * 121)
        marked = (
            f"<!--SECTION:opening-->{prefix} <!--MEMORY:memory-case-->Historia. "
            "<!--SECTION:beat:first-reveal-->Revelación. "
            "<!--SECTION:beat:turn-->Giro. "
            "<!--SECTION:synthesis-->Cierre."
        )
        with self.assertRaises(SectionAlignmentError):
            parse_sectioned_script(marked, PLAN)

    def test_missing_beat_marker_is_rejected(self) -> None:
        marked = "<!--SECTION:opening--><!--MEMORY:memory-case-->Inicio. <!--SECTION:beat:first-reveal-->Caso. <!--SECTION:synthesis-->Cierre."
        with self.assertRaises(SectionAlignmentError):
            parse_sectioned_script(marked, PLAN)


if __name__ == "__main__":
    unittest.main()
