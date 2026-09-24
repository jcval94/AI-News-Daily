import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs" / "examples" / "recording_pack" / "2026-09-04"
PACK_PATH = BASE / "recording_pack.json"
CAMERA_PATH = BASE / "camera_script.md"
TELEPROMPTER_PATH = BASE / "teleprompter.html"
SCRIPT_PATH = ROOT / "scripts" / "2026-09-04" / "script.txt"


class RealRecordingPackReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = json.loads(PACK_PATH.read_text(encoding="utf-8"))
        cls.script = SCRIPT_PATH.read_text(encoding="utf-8").strip()
        cls.camera = CAMERA_PATH.read_text(encoding="utf-8")
        cls.teleprompter = TELEPROMPTER_PATH.read_text(encoding="utf-8")

    def test_pack_is_pinned_to_real_approved_script(self):
        expected = hashlib.sha256(self.script.encode("utf-8")).hexdigest()
        self.assertEqual(self.pack["sources"]["script_sha256"], expected)
        self.assertEqual(self.pack["episode_date"], "2026-09-04")

    def test_editorial_takes_reconstruct_script_exactly(self):
        narration = " ".join(
            take["spoken_text"]
            for take in self.pack["takes"]
            if take["section_kind"] != "cta"
        )
        normalize = lambda value: " ".join(value.split())
        self.assertEqual(normalize(narration), normalize(self.script))

    def test_take_ids_are_unique_and_editorial_durations_are_recordable(self):
        takes = self.pack["takes"]
        ids = [take["take_id"] for take in takes]
        self.assertEqual(len(ids), len(set(ids)))
        editorial = [take for take in takes if take["section_kind"] != "cta"]
        self.assertGreater(len(editorial), 10)
        for take in editorial:
            self.assertGreaterEqual(take["estimated_duration_seconds"], 20.0)
            self.assertLessEqual(take["estimated_duration_seconds"], 60.0)

    def test_cta_is_separate_and_short_take_is_allowed(self):
        cta = [take for take in self.pack["takes"] if take["section_kind"] == "cta"]
        self.assertEqual(len(cta), 1)
        self.assertEqual(cta[0]["take_id"], "cta_t01")
        self.assertLess(cta[0]["estimated_duration_seconds"], 20.0)

    def test_real_pack_keeps_edit_context_without_polluting_spoken_text(self):
        with_cues = [take for take in self.pack["takes"] if take["edit_cues"]]
        self.assertGreater(len(with_cues), 0)
        self.assertEqual(
            len(with_cues),
            self.pack["summary"]["takes_with_edit_cues"],
        )
        for take in with_cues:
            for cue in take["edit_cues"]:
                self.assertTrue(cue["cue_id"])
                self.assertTrue(cue["visual_role"])

    def test_teleprompter_is_standalone_and_contains_every_take(self):
        lower = self.teleprompter.lower()
        self.assertNotIn("http://", lower)
        self.assertNotIn("https://", lower)
        self.assertIn("<!doctype html>", lower)
        for take in self.pack["takes"]:
            self.assertIn(take["take_id"], self.teleprompter)
            self.assertIn(take["take_id"], self.camera)

    def test_readiness_is_correct_before_capture(self):
        readiness = self.pack["readiness"]
        self.assertTrue(readiness["recording_contract_valid"])
        self.assertTrue(readiness["ready_to_record"])
        self.assertFalse(readiness["ready_for_alignment"])
        self.assertIn("recorded_media_required", readiness["blockers_after_recording"])


if __name__ == "__main__":
    unittest.main()
