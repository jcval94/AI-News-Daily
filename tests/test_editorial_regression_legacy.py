from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.editorial_regression import evaluate_episode, exit_code_for_result


class EditorialRegressionLegacyTests(unittest.TestCase):
    def test_legacy_episode_is_renderable_but_never_structurally_passing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            episode = Path(tmp)
            (episode / "script.txt").write_text("Una reflexión editorial histórica con evidencia.", encoding="utf-8")
            (episode / "reviews.json").write_text(
                json.dumps({"editorial": {"score": 9.1}}),
                encoding="utf-8",
            )
            result = evaluate_episode(episode)
            self.assertTrue(result["legacy_contract"])
            self.assertFalse(result["structural_pass"])
            self.assertEqual(result["editorial_score"], 9.1)
            self.assertEqual(exit_code_for_result(result), 0)

    def test_current_runtime_failure_remains_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            episode = Path(tmp)
            (episode / "script.txt").write_text("Borrador incompleto.", encoding="utf-8")
            (episode / "run_state.json").write_text(
                json.dumps({"status": "failure"}),
                encoding="utf-8",
            )
            result = evaluate_episode(episode)
            self.assertFalse(result["legacy_contract"])
            self.assertFalse(result["structural_pass"])
            self.assertEqual(exit_code_for_result(result), 1)


if __name__ == "__main__":
    unittest.main()
