from __future__ import annotations

import unittest

from pipeline.script_sections import SectionAlignmentError, parse_sectioned_script


PLAN = {"stories": [{"selected_news_index": 2}, {"selected_news_index": 5}]}


class ScriptSectionTests(unittest.TestCase):
    def test_markers_create_exact_clean_alignment(self) -> None:
        marked = (
            "<!--SECTION:opening-->Inicio intrigante. "
            "<!--SECTION:story:2-->Primer caso con evidencia. "
            "<!--SECTION:story:5-->Segundo caso que complica la idea. "
            "<!--SECTION:synthesis-->Cierre que transforma el inicio."
        )
        clean, payload = parse_sectioned_script(marked, PLAN)
        self.assertNotIn("SECTION", clean)
        self.assertEqual(
            [item["section_key"] for item in payload["sections"]],
            ["opening", "story:2", "story:5", "synthesis"],
        )
        self.assertIn("Segundo caso", payload["sections"][2]["spoken_text"])

    def test_missing_story_marker_is_rejected(self) -> None:
        marked = "<!--SECTION:opening-->Inicio. <!--SECTION:story:2-->Caso. <!--SECTION:synthesis-->Cierre."
        with self.assertRaises(SectionAlignmentError):
            parse_sectioned_script(marked, PLAN)


if __name__ == "__main__":
    unittest.main()
