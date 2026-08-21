from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from pipeline.run import load_essay_history


class LegacyHistoryTests(unittest.TestCase):
    def test_repository_legacy_episode_is_explicitly_excluded(self) -> None:
        marker = json.loads(Path("scripts/2026-08-21/legacy.json").read_text(encoding="utf-8"))
        self.assertTrue(marker["legacy"])
        self.assertTrue(marker["exclude_from_essay_history"])
        self.assertTrue(marker["exclude_from_voice_dna"])

    def test_legacy_episode_does_not_enter_essay_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root/"2026-08-20"; legacy.mkdir()
            (legacy/"reviews.json").write_text(json.dumps({"approved_for_multimedia": True}))
            (legacy/"legacy.json").write_text(json.dumps({"exclude_from_essay_history": True}))
            (legacy/"script.txt").write_text("HISTORIA 1 noticia 1 Segunda historia")
            modern = root/"2026-08-19"; modern.mkdir()
            (modern/"reviews.json").write_text(json.dumps({"approved_for_multimedia": True}))
            (modern/"episode_plan.json").write_text(json.dumps({"topic_signature": "educacion y criterio", "central_question": "q", "thesis": "t", "narrative_lens": "education", "hook": "h"}))
            (modern/"script.txt").write_text("ensayo moderno")
            essays = load_essay_history(root, date(2026,8,21), 120, 12)
            self.assertEqual(len(essays), 1)
            self.assertEqual(essays[0]["episode_date"], "2026-08-19")


if __name__ == "__main__":
    unittest.main()
