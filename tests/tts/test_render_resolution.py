import json
import tempfile
import unittest
from pathlib import Path

from pipeline.tts.render import resolve_episode


class EpisodeResolutionTests(unittest.TestCase):
    def test_latest_prefers_approved(self):
        root=Path(tempfile.mkdtemp())
        for day,status in [("2026-09-24","approved"),("2026-09-25","failure")]:
            d=root/day; d.mkdir()
            (d/"script_sections.json").write_text('{"sections":[]}')
            (d/"run_state.json").write_text(json.dumps({"status":status}))
        self.assertEqual(resolve_episode("latest",root).name,"2026-09-24")
