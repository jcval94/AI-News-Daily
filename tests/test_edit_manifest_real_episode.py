import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "docs" / "examples" / "edit_manifest" / "2026-09-04" / "edit_manifest.json"
SCRIPT = ROOT / "scripts" / "2026-09-04" / "script.txt"


class RealEditManifestReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        cls.script = SCRIPT.read_text(encoding="utf-8").strip()

    def test_replay_is_pinned_to_real_approved_script(self):
        expected = hashlib.sha256(self.script.encode("utf-8")).hexdigest()
        self.assertEqual(self.payload["sources"]["script_sha256"], expected)
        self.assertEqual(self.payload["episode_date"], "2026-09-04")

    def test_timeline_is_contiguous_and_covers_estimated_duration(self):
        timeline = self.payload["timeline"]
        self.assertTrue(timeline)
        self.assertAlmostEqual(timeline[0]["start_seconds"], 0.0, places=3)
        for left, right in zip(timeline, timeline[1:]):
            self.assertAlmostEqual(
                left["end_seconds"],
                right["start_seconds"],
                places=3,
            )
            self.assertGreater(left["end_seconds"], left["start_seconds"])
        self.assertAlmostEqual(
            timeline[-1]["end_seconds"],
            self.payload["timing"]["duration_seconds"],
            places=3,
        )

    def test_every_media_cue_has_director_signal_and_explicit_asset_state(self):
        media_segments = [
            item for item in self.payload["timeline"] if item["mode"] == "media"
        ]
        self.assertGreater(len(media_segments), 0)
        for item in media_segments:
            self.assertTrue(item["cue_id"])
            director = item["director"]
            self.assertEqual(director["authority"], "suggestion")
            self.assertTrue(director["intent"])
            self.assertTrue(director["visual_role"])
            self.assertTrue(director["transition_in"])
            self.assertTrue(director["treatment"])
            self.assertTrue(director["note"])
            media = item["media"]
            self.assertIn("usable_for_edit", media)
            self.assertIn("blockers", media)

    def test_readiness_cannot_false_green_before_recording_and_assets(self):
        readiness = self.payload["readiness"]
        self.assertTrue(readiness["pre_recording_contract_valid"])
        self.assertTrue(readiness["ready_for_recording"])
        self.assertFalse(readiness["ready_for_automated_timeline_import"])
        self.assertFalse(readiness["asset_resolution_complete"])
        self.assertIn("recording_retime_required", readiness["blockers"])
        self.assertIn("missing_manifest_asset", readiness["blockers"])


if __name__ == "__main__":
    unittest.main()
