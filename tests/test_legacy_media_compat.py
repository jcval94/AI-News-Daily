from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.legacy_media_compat import prepare_legacy_media_episode


class LegacyMediaCompatTests(unittest.TestCase):
    def test_adapter_injects_media_only_structure_without_mutating_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            destination = root / "compat"
            source.mkdir()
            script = " ".join(f"palabra{i}" for i in range(100))
            (source / "script.txt").write_text(script, encoding="utf-8")
            (source / "selected_news.json").write_text(json.dumps({"items": []}), encoding="utf-8")

            injected = prepare_legacy_media_episode(source, destination)

            self.assertTrue(injected)
            self.assertFalse((source / "episode_plan.json").exists())
            self.assertFalse((source / "script_sections.json").exists())
            plan = json.loads((destination / "episode_plan.json").read_text(encoding="utf-8"))
            sections = json.loads((destination / "script_sections.json").read_text(encoding="utf-8"))
            self.assertTrue(plan["media_compatibility_only"])
            self.assertTrue(plan["legacy_contract"])
            self.assertEqual([s["section_key"] for s in sections["sections"]], ["opening", "beat:legacy_body", "synthesis"])
            reconstructed = " ".join(s["spoken_text"] for s in sections["sections"])
            self.assertEqual(reconstructed.split(), script.split())


if __name__ == "__main__":
    unittest.main()
