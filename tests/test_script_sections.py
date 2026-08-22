from __future__ import annotations

import unittest

from pipeline.script_sections import SectionAlignmentError, parse_sectioned_script


PLAN = {
    "beats": [
        {"beat_id": "first-reveal", "kind": "reveal", "evidence_news_indices": [2, 5]},
        {"beat_id": "turn", "kind": "turn", "evidence_news_indices": []},
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
        self.assertEqual(payload["sections"][1]["evidence_news_indices"], [2, 5])
        self.assertEqual(payload["sections"][2]["evidence_news_indices"], [])

    def test_missing_beat_marker_is_rejected(self) -> None:
        marked = "<!--SECTION:opening-->Inicio. <!--SECTION:beat:first-reveal-->Caso. <!--SECTION:synthesis-->Cierre."
        with self.assertRaises(SectionAlignmentError):
            parse_sectioned_script(marked, PLAN)


if __name__ == "__main__":
    unittest.main()
