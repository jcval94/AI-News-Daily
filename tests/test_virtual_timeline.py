import json
import tempfile
import unittest
from pathlib import Path

from pipeline.virtual_timeline import (
    build_virtual_timeline,
    render_timeline_preview,
    write_virtual_timeline,
)


def recording_pack():
    return {
        "episode_date": "2026-09-24",
        "editing_style": {
            "applied": True,
            "style_id": "jc_reflective_essay_v1",
            "sha256": "abc123",
        },
        "capture_recommendation": {
            "resolution": "3840x2160",
            "frame_rate_fps": 30,
            "audio_sample_rate_hz": 48000,
            "aspect_ratio": "16:9",
        },
        "takes": [
            {
                "take_id": "opening_t01",
                "estimated_start_seconds": 0,
                "estimated_end_seconds": 10,
                "estimated_duration_seconds": 10,
                "section_key": "opening",
                "section_kind": "opening",
                "section_label": "Apertura",
                "spoken_text": "Texto de apertura.",
                "delivery": {},
            },
            {
                "take_id": "opening_t02",
                "estimated_start_seconds": 10,
                "estimated_end_seconds": 22,
                "estimated_duration_seconds": 12,
                "section_key": "opening",
                "section_kind": "opening",
                "section_label": "Apertura",
                "spoken_text": "Segundo texto.",
                "delivery": {},
            },
            {
                "take_id": "cta_t01",
                "estimated_start_seconds": 22,
                "estimated_end_seconds": 27,
                "estimated_duration_seconds": 5,
                "section_key": "cta",
                "section_kind": "cta",
                "section_label": "CTA",
                "spoken_text": "CTA final.",
                "delivery": {},
            },
        ],
    }


def edit_manifest():
    return {
        "episode_date": "2026-09-24",
        "timing": {"duration_seconds": 22},
        "editing_style": {
            "applied": True,
            "style_id": "jc_reflective_essay_v1",
            "sha256": "abc123",
        },
        "timeline": [
            {
                "segment_id": "seg_001",
                "mode": "presenter",
                "start_seconds": 0,
                "end_seconds": 3.5,
                "duration_seconds": 3.5,
                "director": {"visual_role": "presenter"},
            },
            {
                "segment_id": "seg_002",
                "mode": "media",
                "cue_id": "slot_001",
                "start_seconds": 3.5,
                "end_seconds": 7,
                "duration_seconds": 3.5,
                "section": {"section_key": "opening"},
                "script_anchor": {"excerpt": "fragmento uno"},
                "director": {
                    "visual_role": "rhythm",
                    "treatment": "natural_motion",
                    "transition_in": "hard_cut",
                    "transition_out": "hard_cut",
                },
                "media": {
                    "usable_for_edit": False,
                    "file": "",
                    "visual_query": "documentary hands",
                    "preferred_asset_type": "video",
                    "blockers": ["missing_manifest_asset"],
                },
            },
            {
                "segment_id": "seg_003",
                "mode": "media",
                "cue_id": "slot_001",
                "start_seconds": 7,
                "end_seconds": 8,
                "duration_seconds": 1,
                "section": {"section_key": "opening"},
                "script_anchor": {"excerpt": "fragmento dos"},
                "director": {
                    "visual_role": "rhythm",
                    "treatment": "natural_motion",
                    "transition_in": "hard_cut",
                    "transition_out": "hard_cut",
                },
                "media": {
                    "usable_for_edit": False,
                    "file": "",
                    "visual_query": "documentary hands",
                    "preferred_asset_type": "video",
                    "blockers": ["missing_manifest_asset"],
                },
            },
            {
                "segment_id": "seg_004",
                "mode": "presenter",
                "start_seconds": 8,
                "end_seconds": 22,
                "duration_seconds": 14,
                "director": {"visual_role": "presenter"},
            },
        ],
    }


class VirtualTimelineTests(unittest.TestCase):
    def test_v1_is_replaceable_take_by_take_and_includes_cta(self):
        payload = build_virtual_timeline(
            recording_pack=recording_pack(),
            edit_manifest=edit_manifest(),
        )
        tracks = {item["track_id"]: item for item in payload["tracks"]}
        v1 = tracks["V1"]["clips"]
        self.assertEqual([item["take_id"] for item in v1], ["opening_t01", "opening_t02", "cta_t01"])
        self.assertEqual([item["replace_key"] for item in v1], ["opening_t01", "opening_t02", "cta_t01"])
        self.assertEqual(v1[-1]["timeline_end_seconds"], 27)
        self.assertEqual(payload["timing"]["approved_script_duration_seconds"], 22)
        self.assertEqual(payload["timing"]["post_script_duration_seconds"], 5)

    def test_split_edit_segments_become_one_v2_cue(self):
        payload = build_virtual_timeline(
            recording_pack=recording_pack(),
            edit_manifest=edit_manifest(),
        )
        tracks = {item["track_id"]: item for item in payload["tracks"]}
        v2 = tracks["V2"]["clips"]
        self.assertEqual(len(v2), 1)
        self.assertEqual(v2[0]["cue_id"], "slot_001")
        self.assertEqual(v2[0]["timeline_start_seconds"], 3.5)
        self.assertEqual(v2[0]["timeline_end_seconds"], 8)
        self.assertEqual(v2[0]["edit_manifest_segment_ids"], ["seg_002", "seg_003"])

    def test_missing_asset_stays_visible_as_placeholder(self):
        payload = build_virtual_timeline(
            recording_pack=recording_pack(),
            edit_manifest=edit_manifest(),
        )
        v2 = next(item for item in payload["tracks"] if item["track_id"] == "V2")
        clip = v2["clips"][0]
        self.assertEqual(clip["kind"], "media_placeholder")
        self.assertEqual(clip["status"], "placeholder")
        self.assertEqual(clip["name"], "documentary hands")
        self.assertIn("missing_manifest_asset", payload["readiness"]["blockers_for_final"])
        self.assertTrue(payload["readiness"]["ready_for_virtual_preview"])

    def test_style_fingerprint_mismatch_fails_closed(self):
        pack = recording_pack()
        edit = edit_manifest()
        edit["editing_style"]["sha256"] = "different"
        with self.assertRaisesRegex(ValueError, "different editing-style fingerprints"):
            build_virtual_timeline(recording_pack=pack, edit_manifest=edit)

    def test_non_contiguous_takes_fail_closed(self):
        pack = recording_pack()
        pack["takes"][1]["estimated_start_seconds"] = 11
        with self.assertRaisesRegex(ValueError, "not contiguous"):
            build_virtual_timeline(recording_pack=pack, edit_manifest=edit_manifest())



    def test_resolved_media_gets_repo_logical_path(self):
        edit = edit_manifest()
        edit["timeline"][1]["media"] = {
            "usable_for_edit": True,
            "file": "assets/slot_001.mp4",
            "asset_type": "video",
            "visual_query": "documentary hands",
            "preferred_asset_type": "video",
            "provider": "pexels",
            "license": "Pexels",
            "blockers": [],
        }
        edit["timeline"][2]["media"] = dict(edit["timeline"][1]["media"])
        payload = build_virtual_timeline(
            recording_pack=recording_pack(),
            edit_manifest=edit,
        )
        v2 = next(item for item in payload["tracks"] if item["track_id"] == "V2")
        source = v2["clips"][0]["source"]
        self.assertEqual(source["media_file"], "assets/slot_001.mp4")
        self.assertEqual(
            source["logical_media_path"],
            "multimedia/2026-09-24/assets/slot_001.mp4",
        )
        self.assertEqual(source["reference_basis"], "repo_root")


    def test_format_and_markers_are_inherited_for_future_nle_export(self):
        payload = build_virtual_timeline(
            recording_pack=recording_pack(),
            edit_manifest=edit_manifest(),
        )
        self.assertEqual(payload["format"]["resolution"], "3840x2160")
        self.assertEqual(payload["format"]["frame_rate_fps"], 30)
        self.assertEqual(payload["format"]["audio_sample_rate_hz"], 48000)
        take_markers = [item for item in payload["markers"] if item["kind"] == "take"]
        section_markers = [item for item in payload["markers"] if item["kind"] == "section"]
        self.assertEqual(len(take_markers), 3)
        self.assertGreaterEqual(len(section_markers), 2)
        self.assertEqual(take_markers[0]["take_id"], "opening_t01")
        self.assertEqual(take_markers[-1]["take_id"], "cta_t01")


    def test_preview_is_standalone_and_contains_tracks(self):
        payload = build_virtual_timeline(
            recording_pack=recording_pack(),
            edit_manifest=edit_manifest(),
        )
        output = render_timeline_preview(payload)
        self.assertIn("<!doctype html>", output.lower())
        self.assertNotIn("http://", output.lower())
        self.assertNotIn("https://", output.lower())
        self.assertIn("Virtual timeline", output)
        self.assertIn("V1", output)
        self.assertIn("slot_001", output)
        self.assertIn("opening_t01", output)

    def test_write_emits_json_and_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode = root / "scripts" / "2026-09-24"
            media = root / "multimedia" / "2026-09-24"
            episode.mkdir(parents=True)
            media.mkdir(parents=True)
            (episode / "recording_pack.json").write_text(
                json.dumps(recording_pack()), encoding="utf-8"
            )
            (media / "edit_manifest.json").write_text(
                json.dumps(edit_manifest()), encoding="utf-8"
            )
            paths = write_virtual_timeline(episode_dir=episode, media_dir=media)
            self.assertTrue(paths[0].exists())
            self.assertTrue(paths[1].exists())
            payload = json.loads(paths[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["take_count"], 3)


if __name__ == "__main__":
    unittest.main()
