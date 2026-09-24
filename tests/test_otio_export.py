import json
import tempfile
import unittest
from pathlib import Path

import opentimelineio as otio

from pipeline.otio_export import (
    build_otio_timeline,
    validate_roundtrip,
    write_otio,
)


def virtual_payload():
    return {
        "schema_version": 1,
        "episode_date": "2026-09-24",
        "status": "pre_recording_virtual_timeline",
        "timing": {
            "duration_seconds": 20.0,
            "frame_rate_fps": 30,
            "frame_accurate": False,
            "requires_recording_retime": True,
        },
        "format": {
            "resolution": "3840x2160",
            "frame_rate_fps": 30,
            "audio_sample_rate_hz": 48000,
            "aspect_ratio": "16:9",
        },
        "editing_style": {
            "applied": True,
            "style_id": "jc_reflective_essay_v1",
            "sha256": "abc123",
        },
        "replacement_contract": {
            "virtual_a_roll_authority": "take_id",
            "strategy": "replace_and_retime_after_alignment",
            "real_a_roll_may_change_duration": True,
            "retime_b_roll_after_alignment": True,
            "never_treat_estimated_seconds_as_source_timecode": True,
        },
        "readiness": {
            "virtual_timeline_contract_valid": True,
            "ready_for_virtual_preview": True,
            "ready_for_real_a_roll_replace": False,
            "ready_for_automated_nle_import": False,
            "blockers_for_final": ["recorded_media_required"],
        },
        "sources": {},
        "markers": [
            {
                "marker_id": "section_01",
                "kind": "section",
                "timeline_seconds": 0,
                "label": "Apertura",
                "section_key": "opening",
            },
            {
                "marker_id": "take_opening_t01",
                "kind": "take",
                "timeline_seconds": 0,
                "label": "opening_t01",
                "take_id": "opening_t01",
            },
            {
                "marker_id": "take_opening_t02",
                "kind": "take",
                "timeline_seconds": 10,
                "label": "opening_t02",
                "take_id": "opening_t02",
            },
        ],
        "tracks": [
            {"track_id": "V4", "kind": "titles", "name": "Titles", "clips": []},
            {"track_id": "V3", "kind": "graphics", "name": "Graphics", "clips": []},
            {
                "track_id": "V2",
                "kind": "b_roll",
                "name": "B-roll",
                "clips": [
                    {
                        "clip_id": "broll_001_slot_001",
                        "kind": "media_placeholder",
                        "status": "placeholder",
                        "cue_id": "slot_001",
                        "name": "evidence placeholder",
                        "timeline_start_seconds": 4,
                        "timeline_end_seconds": 8,
                        "duration_seconds": 4,
                        "source": {
                            "type": "generated_placeholder",
                            "media_file": None,
                            "blockers": ["missing_manifest_asset"],
                        },
                        "director": {"visual_role": "evidence"},
                    },
                    {
                        "clip_id": "broll_002_slot_002",
                        "kind": "media_asset",
                        "status": "resolved",
                        "cue_id": "slot_002",
                        "name": "resolved video",
                        "timeline_start_seconds": 12,
                        "timeline_end_seconds": 16,
                        "duration_seconds": 4,
                        "source": {
                            "type": "file",
                            "media_file": "../../multimedia/2026-09-24/clip.mp4",
                            "asset_type": "video",
                            "usable_for_edit": True,
                            "blockers": [],
                        },
                        "director": {"visual_role": "context"},
                    },
                ],
            },
            {
                "track_id": "V1",
                "kind": "presenter",
                "name": "JC virtual A-roll",
                "clips": [
                    {
                        "clip_id": "aroll_001_opening_t01",
                        "kind": "virtual_a_roll",
                        "status": "placeholder",
                        "take_id": "opening_t01",
                        "name": "JC · opening_t01",
                        "timeline_start_seconds": 0,
                        "timeline_end_seconds": 10,
                        "duration_seconds": 10,
                        "replace_key": "opening_t01",
                        "source": {
                            "type": "generated_placeholder",
                            "media_file": None,
                            "recorded_media_required": True,
                        },
                    },
                    {
                        "clip_id": "aroll_002_opening_t02",
                        "kind": "virtual_a_roll",
                        "status": "placeholder",
                        "take_id": "opening_t02",
                        "name": "JC · opening_t02",
                        "timeline_start_seconds": 10,
                        "timeline_end_seconds": 20,
                        "duration_seconds": 10,
                        "replace_key": "opening_t02",
                        "source": {
                            "type": "generated_placeholder",
                            "media_file": None,
                            "recorded_media_required": True,
                        },
                    },
                ],
            },
            {
                "track_id": "A1",
                "kind": "dialogue",
                "name": "JC dialogue placeholder",
                "clips": [
                    {
                        "clip_id": "audio_opening_t01",
                        "kind": "virtual_dialogue",
                        "status": "placeholder",
                        "take_id": "opening_t01",
                        "name": "JC · opening_t01",
                        "timeline_start_seconds": 0,
                        "timeline_end_seconds": 10,
                        "duration_seconds": 10,
                        "replace_key": "opening_t01",
                        "source": {
                            "type": "generated_placeholder",
                            "media_file": None,
                            "recorded_media_required": True,
                        },
                    },
                    {
                        "clip_id": "audio_opening_t02",
                        "kind": "virtual_dialogue",
                        "status": "placeholder",
                        "take_id": "opening_t02",
                        "name": "JC · opening_t02",
                        "timeline_start_seconds": 10,
                        "timeline_end_seconds": 20,
                        "duration_seconds": 10,
                        "replace_key": "opening_t02",
                        "source": {
                            "type": "generated_placeholder",
                            "media_file": None,
                            "recorded_media_required": True,
                        },
                    },
                ],
            },
        ],
    }


class OtioExportTests(unittest.TestCase):
    def test_build_preserves_track_order_and_duration(self):
        payload = virtual_payload()
        timeline = build_otio_timeline(payload, output_dir=Path("."))
        track_ids = [
            track.metadata["ai_news_daily"]["track_id"]
            for track in timeline.tracks
        ]
        self.assertEqual(track_ids, ["V4", "V3", "V2", "V1", "A1"])
        self.assertAlmostEqual(
            timeline.duration().value / timeline.duration().rate,
            20.0,
            places=3,
        )

    def test_sparse_broll_uses_gaps_and_preserves_positions(self):
        timeline = build_otio_timeline(virtual_payload(), output_dir=Path("."))
        v2 = timeline.tracks[2]
        self.assertIsInstance(v2[0], otio.schema.Gap)
        self.assertIsInstance(v2[1], otio.schema.Clip)
        self.assertIsInstance(v2[2], otio.schema.Gap)
        self.assertIsInstance(v2[3], otio.schema.Clip)
        self.assertIsInstance(v2[4], otio.schema.Gap)
        self.assertEqual(v2[1].metadata["ai_news_daily"]["cue_id"], "slot_001")
        self.assertEqual(v2[3].metadata["ai_news_daily"]["cue_id"], "slot_002")

    def test_missing_and_external_media_references_are_explicit(self):
        timeline = build_otio_timeline(virtual_payload(), output_dir=Path("."))
        v2 = timeline.tracks[2]
        missing = v2[1]
        resolved = v2[3]
        self.assertIsInstance(missing.media_reference, otio.schema.MissingReference)
        self.assertIsInstance(resolved.media_reference, otio.schema.ExternalReference)
        self.assertEqual(
            resolved.media_reference.target_url,
            "../../multimedia/2026-09-24/clip.mp4",
        )

    def test_take_markers_live_on_timeline_stack(self):
        timeline = build_otio_timeline(virtual_payload(), output_dir=Path("."))
        self.assertEqual(len(timeline.tracks.markers), 3)
        self.assertEqual(timeline.tracks.markers[0].name, "Apertura")
        self.assertEqual(
            timeline.tracks.markers[-1].metadata["ai_news_daily"]["take_id"],
            "opening_t02",
        )

    def test_roundtrip_validation_checks_structure(self):
        payload = virtual_payload()
        timeline = build_otio_timeline(payload, output_dir=Path("."))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "timeline.otio"
            otio.adapters.write_to_file(
                timeline, str(path), adapter_name="otio_json"
            )
            reloaded = otio.adapters.read_from_file(
                str(path), adapter_name="otio_json"
            )
            result = validate_roundtrip(
                source_payload=payload,
                timeline=reloaded,
            )
        self.assertTrue(result["valid"])
        self.assertEqual(result["track_ids"], ["V4", "V3", "V2", "V1", "A1"])
        self.assertEqual(result["clip_count"], 6)
        self.assertEqual(result["marker_count"], 3)

    def test_write_emits_native_otio_and_validation_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            episode = Path(tmp) / "scripts" / "2026-09-24"
            episode.mkdir(parents=True)
            (episode / "virtual_timeline.json").write_text(
                json.dumps(virtual_payload()), encoding="utf-8"
            )
            otio_path, validation_path = write_otio(episode_dir=episode)
            self.assertTrue(otio_path.exists())
            self.assertTrue(validation_path.exists())
            reloaded = otio.adapters.read_from_file(str(otio_path))
            self.assertIsInstance(reloaded, otio.schema.Timeline)
            validation = json.loads(validation_path.read_text(encoding="utf-8"))
            self.assertTrue(validation["valid"])
            self.assertEqual(validation["adapter"], "otio_json")
            self.assertFalse(validation["frame_accurate"])
            self.assertTrue(validation["requires_recording_retime"])

    def test_overlapping_sparse_track_fails_closed(self):
        payload = virtual_payload()
        payload["tracks"][2]["clips"][1]["timeline_start_seconds"] = 7
        with self.assertRaisesRegex(ValueError, "overlapping clips"):
            build_otio_timeline(payload, output_dir=Path("."))


if __name__ == "__main__":
    unittest.main()
