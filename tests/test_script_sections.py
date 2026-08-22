from __future__ import annotations

import unittest

from pipeline.script_sections import SectionAlignmentError, parse_sectioned_script


PLAN = {
    "beats": [
        {"beat_id": "first-reveal", "kind": "reveal", "evidence_ids": ["case-a", "case-b"]},
        {"beat_id": "turn", "kind": "turn", "evidence_ids": []},
    ]
}


class ScriptSectionTests(unittest.TestCase):
    def test_markers_follow_idea_beats_not_news_items(self) -> None:
        marked = (
            "<!--SECTION:opening-->Inicio intrigante. "
            "<!--SECTION:beat:first-reveal-->Dos casos se comparan dentro del mismo argumento. "
            "<!--SECTION:beat:turn-->Aquí cambia la pregunta sin introducir otra noticia. "
            "<!--SECTION:synthesis-->Cierre que transforma el inicio."
        )
        clean, payload = parse_sectioned_script(marked, PLAN)
        self.assertNotIn("SECTION", clean)
        self.assertEqual(
            [item["section_key"] for item in payload["sections"]],
            ["opening", "beat:first-reveal", "beat:turn", "synthesis"],
        )
        self.assertEqual(payload["sections"][1]["evidence_ids"], ["case-a", "case-b"])
        self.assertEqual(payload["sections"][2]["evidence_ids"], [])

    def test_trailing_marker_only_debris_is_ignored(self) -> None:
        marked = (
            "<!--SECTION:opening-->Inicio. "
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
            "<!--SECTION:opening-->Inicio. "
            "<!--SECTION:beat:first-reveal-->Revelación. "
            "<!--SECTION:beat:turn-->Giro. "
            "<!--SECTION:synthesis-->Cierre. "
            "<!--SECTION:beat:first-reveal-->Texto que no pertenece al cierre."
        )
        with self.assertRaises(SectionAlignmentError):
            parse_sectioned_script(marked, PLAN)

    def test_missing_beat_marker_is_rejected(self) -> None:
        marked = "<!--SECTION:opening-->Inicio. <!--SECTION:beat:first-reveal-->Caso. <!--SECTION:synthesis-->Cierre."
        with self.assertRaises(SectionAlignmentError):
            parse_sectioned_script(marked, PLAN)


if __name__ == "__main__":
    unittest.main()
