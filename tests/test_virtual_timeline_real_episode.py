import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs" / "examples" / "virtual_timeline" / "2026-09-04"
TIMELINE_PATH = BASE / "virtual_timeline.json"
PREVIEW_PATH = BASE / "timeline_preview.html"


class RealVirtualTimelineReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(TIMELINE_PATH.read_text(encoding="utf-8"))
        cls.preview = PREVIEW_PATH.read_text(encoding="utf-8")
        cls.tracks = {item["track_id"]: item for item in cls.payload["tracks"]}

    def test_real_replay_contains_full_recording_pack(self):
        self.assertEqual(self.payload["episode_date"], "2026-09-04")
        self.assertEqual(self.payload["summary"]["take_count"], 25)
        self.assertEqual(len(self.tracks["V1"]["clips"]), 25)
        self.assertEqual(len(self.tracks["A1"]["clips"]), 25)
        self.assertEqual(
            [item["take_id"] for item in self.tracks["V1"]["clips"]],
            [item["take_id"] for item in self.tracks["A1"]["clips"]],
        )

    def test_v1_is_contiguous_through_cta(self):
        clips = self.tracks["V1"]["clips"]
        self.assertEqual(clips[0]["timeline_start_seconds"], 0)
        for previous, current in zip(clips, clips[1:]):
            self.assertAlmostEqual(
                previous["timeline_end_seconds"],
                current["timeline_start_seconds"],
                places=3,
            )
        self.assertEqual(clips[-1]["take_id"], "cta_t01")
        self.assertAlmostEqual(clips[-1]["timeline_end_seconds"], 917.6, places=1)
        self.assertAlmostEqual(
            self.payload["timing"]["post_script_duration_seconds"], 14.0, places=1
        )

    def test_real_media_cues_remain_visible_when_assets_are_missing(self):
        v2 = self.tracks["V2"]["clips"]
        self.assertEqual(len(v2), 15)
        self.assertEqual(self.payload["summary"]["media_placeholder_count"], 15)
        self.assertEqual(self.payload["summary"]["resolved_media_count"], 0)
        self.assertTrue(all(item["kind"] == "media_placeholder" for item in v2))
        self.assertTrue(all(item["cue_id"] for item in v2))
        self.assertIn(
            "missing_manifest_asset",
            self.payload["readiness"]["blockers_for_final"],
        )

    def test_replay_is_preview_ready_but_not_false_green_for_final_edit(self):
        readiness = self.payload["readiness"]
        self.assertTrue(readiness["virtual_timeline_contract_valid"])
        self.assertTrue(readiness["ready_for_virtual_preview"])
        self.assertFalse(readiness["ready_for_real_a_roll_replace"])
        self.assertFalse(readiness["ready_for_automated_nle_import"])
        self.assertIn("recorded_media_required", readiness["blockers_for_final"])
        self.assertIn("recording_retime_required", readiness["blockers_for_final"])


    def test_real_replay_carries_capture_format_and_markers(self):
        self.assertEqual(self.payload["format"]["resolution"], "3840x2160")
        self.assertEqual(self.payload["format"]["frame_rate_fps"], 30)
        self.assertEqual(self.payload["format"]["audio_sample_rate_hz"], 48000)
        take_markers = [item for item in self.payload["markers"] if item["kind"] == "take"]
        self.assertEqual(len(take_markers), 25)
        self.assertEqual(take_markers[0]["take_id"], "opening_t01")
        self.assertEqual(take_markers[-1]["take_id"], "cta_t01")


    def test_preview_is_standalone_and_exposes_track_ids(self):
        lower = self.preview.lower()
        self.assertIn("<!doctype html>", lower)
        self.assertNotIn("http://", lower)
        self.assertNotIn("https://", lower)
        for track_id in ("V4", "V3", "V2", "V1", "A1"):
            self.assertIn(track_id, self.preview)
        self.assertIn("opening_t01", self.preview)
        self.assertIn("slot_001", self.preview)


if __name__ == "__main__":
    unittest.main()
