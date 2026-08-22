from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.editorial_regression import evaluate_episode


class EditorialRegressionRuntimeTests(unittest.TestCase):
    def test_current_runtime_fixture_requires_beats_and_rejects_news_numbering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "script.txt").write_text("No sé si te pasa.\n\n## Evidencia 1\nUn caso.", encoding="utf-8")
            (root / "episode_plan.json").write_text(json.dumps({
                "evidence": [{"selected_news_index": 1}],
                "beats": [{"beat_id": "turn", "evidence_news_indices": [1]}],
            }), encoding="utf-8")
            (root / "script_sections.json").write_text(json.dumps({"sections": [
                {"section_key": "opening", "spoken_text": "No sé si te pasa."},
                {"section_key": "beat:turn", "spoken_text": "Un caso."},
                {"section_key": "synthesis", "spoken_text": "Cierre."},
            ]}), encoding="utf-8")
            result = evaluate_episode(root)
            self.assertFalse(result["structural_pass"])
            self.assertFalse(result["structural_checks"]["no_news_numbered_headings"])
            self.assertTrue(result["structural_checks"]["uses_idea_led_beats"])


if __name__ == "__main__":
    unittest.main()
