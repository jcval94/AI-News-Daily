from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.review_hub_v14 import apply_script_structure, build_script_structure_payload


class ScriptStructureMapTests(unittest.TestCase):
    def _episode_dir(self) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "script_sections.json").write_text(
            json.dumps(
                {
                    "schema_version": 4,
                    "sections": [
                        {
                            "section_key": "opening",
                            "kind": "opening",
                            "beat_id": None,
                            "beat_kind": None,
                            "evidence_ids": [],
                            "spoken_text": "Abrimos con una tensión concreta y una historia.",
                            "word_count": 8,
                        },
                        {
                            "section_key": "beat:first-reveal",
                            "kind": "development",
                            "beat_id": "first-reveal",
                            "beat_kind": "reveal",
                            "evidence_ids": ["agent-news"],
                            "spoken_text": "La noticia actual cambia la escala del argumento.",
                            "word_count": 8,
                        },
                        {
                            "section_key": "synthesis",
                            "kind": "synthesis",
                            "beat_id": None,
                            "beat_kind": None,
                            "evidence_ids": [],
                            "spoken_text": "Cerramos regresando a la pregunta inicial.",
                            "word_count": 7,
                        },
                    ],
                    "narrative_memory": {
                        "primary_memory_id": "plato-writing-memory",
                        "opening_memory_id": "plato-writing-memory",
                        "placement": "opening",
                        "section_key": "opening",
                        "marker_words_from_section_start": 4,
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (root / "episode_plan.json").write_text(
            json.dumps(
                {
                    "primary_memory_id": "plato-writing-memory",
                    "narrative_parallels": [
                        {
                            "memory_id": "plato-writing-memory",
                            "role": "historical_mirror",
                            "placement": "opening",
                            "purpose": "Abrir con un espejo histórico.",
                        }
                    ],
                    "evidence": [
                        {
                            "evidence_id": "agent-news",
                            "selected_news_index": 1,
                            "role": "anchor",
                            "argument_role": "evidence",
                        }
                    ],
                    "beats": [
                        {
                            "beat_id": "first-reveal",
                            "kind": "reveal",
                            "purpose": "Mostrar el cambio de escala.",
                            "estimated_minutes": 1.0,
                            "evidence_ids": ["agent-news"],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (root / "selected_news.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "selected_news_index": 1,
                            "title": "Agentes de IA llegan a producción",
                            "source": "Example",
                            "url": "https://example.com/story",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (root / "narrative_memory_selection.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "id": "plato-writing-memory",
                            "title": "Platón, la escritura y la memoria externa",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return root

    def _document(self) -> str:
        return """<!doctype html>
<html>
<head><style>.script{white-space:pre-wrap}</style></head>
<body>
<section id="guion"><h2>Guion actual</h2><div id="scriptText" class="script" data-search-script>Texto</div></section>
</body>
</html>"""

    def test_builds_semantic_map_from_pipeline_metadata(self) -> None:
        payload = build_script_structure_payload(self._episode_dir())
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual([item["label"] for item in payload["sections"]], ["Introducción", "Revelación", "Cierre"])
        self.assertEqual(payload["narrative_memory"]["section_index"], 0)
        self.assertEqual(payload["narrative_memory"]["marker_words_from_section_start"], 4)
        self.assertEqual(payload["sections"][1]["evidence"][0]["title"], "Agentes de IA llegan a producción")
        self.assertEqual(payload["sections"][1]["evidence"][0]["selected_news_index"], 1)

    def test_injects_clickable_map_and_runtime(self) -> None:
        payload = build_script_structure_payload(self._episode_dir())
        rendered = apply_script_structure(self._document(), structure_payload=payload)
        self.assertIn('id="scriptStructure"', rendered)
        self.assertIn('data-script-structure-runtime="v1"', rendered)
        self.assertIn("Mapa del guion", rendered)
        self.assertIn("Introducción", rendered)
        self.assertIn("Cierre", rendered)
        self.assertIn("Historia · Platón, la escritura y la memoria externa", rendered)
        self.assertIn("Noticia 1 · Agentes de IA llegan a producción", rendered)
        self.assertIn("data-script-memory-jump", rendered)

    def test_missing_metadata_is_safe_for_legacy_episode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(build_script_structure_payload(Path(tmp)))
        self.assertEqual(
            apply_script_structure(self._document(), structure_payload=None),
            self._document(),
        )

    def test_layer_is_idempotent(self) -> None:
        payload = build_script_structure_payload(self._episode_dir())
        once = apply_script_structure(self._document(), structure_payload=payload)
        twice = apply_script_structure(once, structure_payload=payload)
        self.assertEqual(once, twice)
        self.assertEqual(once.count('data-script-structure-runtime="v1"'), 1)


if __name__ == "__main__":
    unittest.main()
