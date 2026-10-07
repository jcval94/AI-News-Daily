from __future__ import annotations

import unittest

from pipeline.script_sections import (
    SectionAlignmentError,
    materialize_writer_draft,
    parse_sectioned_script,
    writer_marker_contract,
    writer_structure_repair_prompt,
    writer_structured_contract,
)


PLAN = {
    "primary_memory_id": "memory-case",
    "opening_memory_id": "memory-case",
    "narrative_parallels": [
        {
            "memory_id": "memory-case",
            "placement": "opening",
            "role": "historical_mirror",
            "purpose": "Abrir con un caso verificado.",
            "limits": "No asumir causalidad idéntica.",
        }
    ],
    "beats": [
        {"beat_id": "first-reveal", "kind": "reveal", "evidence_ids": ["case-a", "case-b"]},
        {"beat_id": "turn", "kind": "turn", "evidence_ids": []},
    ]
}


class ScriptSectionTests(unittest.TestCase):
    def test_writer_contract_names_the_actual_allowed_turn_section(self):
        import copy
        plan = copy.deepcopy(PLAN)
        plan['opening_memory_id'] = None
        plan['narrative_parallels'][0]['placement'] = 'narrative_turn'
        contract = writer_marker_contract(plan)
        self.assertIn('inside ONE of these sections: beat:turn.', contract)
        self.assertEqual(contract.count('<!--MEMORY:memory-case-->'), 1)
        self.assertNotIn('inside ONE of these sections: opening', contract)

    def test_structure_repair_prompt_reuses_invalid_draft_instead_of_regenerating(self) -> None:
        previous = {
            "opening": "Inicio.",
            "beats": ["Revelación.", "Giro."],
            "synthesis": "Cierre.",
            "primary_memory_section_index": 2,
        }
        prompt = writer_structure_repair_prompt(
            previous,
            "primary_memory_section_index must respect the planned placement",
            PLAN,
        )
        self.assertIn('"opening": "Inicio."', prompt)
        self.assertIn("do not write a new essay from scratch", prompt)
        self.assertIn("Validation error to repair:", prompt)
        self.assertIn("Structured output contract:", prompt)
        self.assertIn("complete corrected structured draft", prompt)

    def test_structured_writer_contract_exposes_dynamic_beat_order(self) -> None:
        contract = writer_structured_contract(PLAN)
        self.assertIn("exactly 2 beats", contract)
        self.assertIn("beat_id=first-reveal", contract)
        self.assertIn("beat_id=turn", contract)
        self.assertIn("primary_memory_section_index must be one of [0]", contract)
        self.assertIn("Python adds them deterministically", contract)

    def test_materialize_writer_draft_builds_exact_markers(self) -> None:
        structured = {
            "opening": "Inicio intrigante.",
            "beats": [
                "Dos casos se comparan dentro del mismo argumento.",
                "Aquí cambia la pregunta sin introducir otra noticia.",
            ],
            "synthesis": "Cierre que transforma el inicio.",
            "primary_memory_section_index": 0,
        }
        marked = materialize_writer_draft(structured, PLAN)
        self.assertEqual(marked.count("<!--SECTION:"), 4)
        self.assertEqual(marked.count("<!--MEMORY:memory-case-->"), 1)
        self.assertTrue(
            marked.startswith(
                "<!--SECTION:opening--><!--MEMORY:memory-case-->Inicio intrigante."
            )
        )
        clean, payload = parse_sectioned_script(marked, PLAN)
        self.assertNotIn("SECTION", clean)
        self.assertEqual(
            [item["section_key"] for item in payload["sections"]],
            ["opening", "beat:first-reveal", "beat:turn", "synthesis"],
        )

    def test_materialize_writer_draft_rejects_wrong_beat_count(self) -> None:
        structured = {
            "opening": "Inicio.",
            "beats": ["Sólo un beat."],
            "synthesis": "Cierre.",
            "primary_memory_section_index": 0,
        }
        with self.assertRaisesRegex(
            SectionAlignmentError, "exactly 2 items"
        ):
            materialize_writer_draft(structured, PLAN)

    def test_materialize_writer_draft_enforces_turn_memory_index(self) -> None:
        import copy
        plan = copy.deepcopy(PLAN)
        plan["opening_memory_id"] = None
        plan["narrative_parallels"][0]["placement"] = "narrative_turn"
        structured = {
            "opening": "Inicio.",
            "beats": ["Revelación.", "El caso histórico abre este giro."],
            "synthesis": "Cierre.",
            "primary_memory_section_index": 2,
        }
        marked = materialize_writer_draft(structured, plan)
        self.assertIn(
            "<!--SECTION:beat:turn--><!--MEMORY:memory-case-->",
            marked,
        )
        bad = {**structured, "primary_memory_section_index": 1}
        with self.assertRaisesRegex(
            SectionAlignmentError, "planned placement"
        ):
            materialize_writer_draft(bad, plan)

    def test_materialize_writer_draft_rejects_model_generated_markers(self) -> None:
        structured = {
            "opening": "<!--SECTION:opening-->Inicio.",
            "beats": ["Revelación.", "Giro."],
            "synthesis": "Cierre.",
            "primary_memory_section_index": 0,
        }
        with self.assertRaisesRegex(SectionAlignmentError, "must not contain hidden"):
            materialize_writer_draft(structured, PLAN)

    def test_materialize_writer_draft_supports_closing_callback(self) -> None:
        import copy
        plan = copy.deepcopy(PLAN)
        plan["opening_memory_id"] = None
        plan["narrative_parallels"][0]["placement"] = "closing_callback"
        structured = {
            "opening": "Inicio.",
            "beats": ["Revelación.", "Giro."],
            "synthesis": "La memoria abre el cierre.",
            "primary_memory_section_index": 3,
        }
        marked = materialize_writer_draft(structured, plan)
        self.assertIn(
            "<!--SECTION:synthesis--><!--MEMORY:memory-case-->",
            marked,
        )

    def test_materialize_writer_draft_support_uses_declared_development_beat(self) -> None:
        import copy
        plan = copy.deepcopy(PLAN)
        plan["opening_memory_id"] = None
        plan["narrative_parallels"][0]["placement"] = "support"
        structured = {
            "opening": "Inicio.",
            "beats": ["La memoria apoya esta revelación.", "Giro."],
            "synthesis": "Cierre.",
            "primary_memory_section_index": 1,
        }
        marked = materialize_writer_draft(structured, plan)
        self.assertIn(
            "<!--SECTION:beat:first-reveal--><!--MEMORY:memory-case-->",
            marked,
        )

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
