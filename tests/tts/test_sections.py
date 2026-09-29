import json
import tempfile
import unittest
from pathlib import Path

from pipeline.tts.sections import load_spoken_sections, normalize_spoken_text, safe_section_filename


class TTSSectionTests(unittest.TestCase):
    def test_normalization_removes_non_spoken_markup(self):
        value = '<!--MEMORY:x--> **OpenAI** [fuente](https://example.com) <span>LLM</span>'
        self.assertEqual(normalize_spoken_text(value, {"LLM":"ele ele eme"}), "OpenAI fuente ele ele eme")

    def test_loads_semantic_sections_without_metadata(self):
        root = Path(tempfile.mkdtemp())
        payload = {"schema_version":4,"sections":[
            {"section_key":"opening","kind":"opening","spoken_text":"Hola **mundo**.","evidence_ids":[]},
            {"section_key":"beat:x","kind":"development","spoken_text":"AI y LLM.","evidence_ids":["n1"]}
        ]}
        (root/"script_sections.json").write_text(json.dumps(payload),encoding="utf-8")
        sections, raw = load_spoken_sections(root, pronunciations={"LLM":"ele ele eme"})
        self.assertEqual(raw["schema_version"],4)
        self.assertEqual([x["id"] for x in sections],["opening","beat:x"])
        self.assertEqual(sections[1]["spoken_text"],"AI y ele ele eme.")
        self.assertNotIn("MEMORY", sections[0]["spoken_text"])

    def test_missing_sections_fail_closed(self):
        root=Path(tempfile.mkdtemp())
        (root/"script_sections.json").write_text('{"schema_version":4,"sections":[]}',encoding="utf-8")
        with self.assertRaises(ValueError):
            load_spoken_sections(root)

    def test_filename_is_stable_and_safe(self):
        self.assertEqual(safe_section_filename(2,"beat:¿Qué pasó?"),"02_beat-qu-pas")
