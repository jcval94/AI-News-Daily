from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pipeline.evidence_reconciliation import reconcile_episode_dir


class EvidenceReconciliationLegacyTests(unittest.TestCase):
    def test_missing_episode_plan_is_explicit_legacy_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            episode = Path(tmp)
            (episode / "script.txt").write_text("Legacy canonical script.", encoding="utf-8")
            reconciled, changes = reconcile_episode_dir(episode, write=True)
            self.assertEqual(changes, [])
            metadata = reconciled["evidence_reconciliation"]
            self.assertTrue(metadata["skipped"])
            self.assertFalse(metadata["changed"])
            self.assertIn("no episode_plan.json", metadata["reason"])
            self.assertFalse((episode / "episode_plan.json").exists())


if __name__ == "__main__":
    unittest.main()
