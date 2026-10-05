import json
import tempfile
import unittest
from pathlib import Path

from pipeline.tts.render import resolve_episode


class EpisodeResolutionTests(unittest.TestCase):
    def test_latest_prefers_approved(self):
        root = Path(tempfile.mkdtemp())
        for day, status in [("2026-09-24", "approved"), ("2026-09-25", "failure")]:
            episode = root / day
            episode.mkdir()
            (episode / "script_sections.json").write_text('{"sections":[]}')
            (episode / "run_state.json").write_text(json.dumps({"status": status}))
        self.assertEqual(resolve_episode("latest", root).name, "2026-09-24")

    def test_unapproved_and_missing_state_fail_closed(self):
        root = Path(tempfile.mkdtemp())
        for day, state in [("2026-09-24", None), ("2026-09-25", "failure")]:
            episode = root / day
            episode.mkdir()
            (episode / "script_sections.json").write_text('{"sections":[]}')
            if state:
                (episode / "run_state.json").write_text(json.dumps({"status": state}))

        with self.assertRaises(FileNotFoundError):
            resolve_episode("latest", root)
        with self.assertRaises(ValueError):
            resolve_episode("2026-09-25", root)
