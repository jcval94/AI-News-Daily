import json
import tempfile
import unittest
from pathlib import Path

import opentimelineio as otio

from pipeline.otio_export import build_otio_timeline, validate_roundtrip


ROOT = Path(__file__).resolve().parents[1]
REAL_VIRTUAL_TIMELINE = (
    ROOT
    / "docs"
    / "examples"
    / "virtual_timeline"
    / "2026-09-04"
    / "virtual_timeline.json"
)


class RealOtioExportReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(REAL_VIRTUAL_TIMELINE.read_text(encoding="utf-8"))

    def test_real_episode_builds_expected_otio_structure(self):
        timeline = build_otio_timeline(self.payload, output_dir=Path("."))
        track_ids = [
            track.metadata["ai_news_daily"]["track_id"]
            for track in timeline.tracks
        ]
        self.assertEqual(track_ids, ["V4", "V3", "V2", "V1", "A1"])
        self.assertAlmostEqual(
            timeline.duration().value / timeline.duration().rate,
            917.6,
            places=2,
        )
        self.assertEqual(len(timeline.tracks.markers), 36)

        clip_count = sum(
            1
            for track in timeline.tracks
            for item in track
            if isinstance(item, otio.schema.Clip)
        )
        self.assertEqual(clip_count, 65)

    def test_real_v1_and_a1_keep_all_take_ids(self):
        timeline = build_otio_timeline(self.payload, output_dir=Path("."))
        for track_index in (3, 4):
            clips = [
                item
                for item in timeline.tracks[track_index]
                if isinstance(item, otio.schema.Clip)
            ]
            self.assertEqual(len(clips), 25)
            take_ids = [
                item.metadata["ai_news_daily"]["take_id"]
                for item in clips
            ]
            self.assertEqual(take_ids[0], "opening_t01")
            self.assertEqual(take_ids[-1], "cta_t01")

    def test_real_v2_keeps_all_media_placeholders(self):
        timeline = build_otio_timeline(self.payload, output_dir=Path("."))
        clips = [
            item
            for item in timeline.tracks[2]
            if isinstance(item, otio.schema.Clip)
        ]
        self.assertEqual(len(clips), 15)
        self.assertTrue(
            all(
                isinstance(item.media_reference, otio.schema.MissingReference)
                for item in clips
            )
        )
        self.assertEqual(
            clips[0].metadata["ai_news_daily"]["cue_id"],
            "slot_001",
        )

    def test_real_episode_roundtrips_losslessly_for_contract_fields(self):
        timeline = build_otio_timeline(self.payload, output_dir=Path("."))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "timeline.otio"
            otio.adapters.write_to_file(
                timeline,
                str(path),
                adapter_name="otio_json",
            )
            reloaded = otio.adapters.read_from_file(
                str(path),
                adapter_name="otio_json",
            )
            validation = validate_roundtrip(
                source_payload=self.payload,
                timeline=reloaded,
            )
        self.assertTrue(validation["valid"])
        self.assertAlmostEqual(validation["duration_seconds"], 917.6, places=2)
        self.assertEqual(validation["clip_count"], 65)
        self.assertEqual(validation["marker_count"], 36)
        self.assertEqual(
            validation["track_ids"],
            ["V4", "V3", "V2", "V1", "A1"],
        )


if __name__ == "__main__":
    unittest.main()
