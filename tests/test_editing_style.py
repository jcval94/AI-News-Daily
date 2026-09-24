import copy
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.editing_style import (
    KNOWN_VISUAL_ROLES,
    lint_timeline,
    load_editing_style,
    media_defaults,
    validate_editing_style,
)


ROOT = Path(__file__).resolve().parents[1]
STYLE_PATH = ROOT / "config" / "editing_style.yaml"
REAL_EDIT_REPLAY = ROOT / "docs" / "examples" / "edit_manifest" / "2026-09-04" / "edit_manifest.json"


class EditingStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.style = load_editing_style(STYLE_PATH)

    def test_repository_style_contract_is_valid(self):
        self.assertEqual(self.style["schema_version"], 1)
        self.assertEqual(self.style["style_id"], "jc_reflective_essay_v1")
        self.assertEqual(
            set(self.style["visual_roles"]),
            KNOWN_VISUAL_ROLES,
        )
        self.assertEqual(self.style["enforcement"]["mode"], "observe")
        self.assertFalse(self.style["enforcement"]["promotion_blocking"])
        self.assertTrue(self.style["_sha256"])

    def test_evidence_defaults_are_documentary_not_decorative(self):
        image = media_defaults(self.style, role="evidence", asset_type="image")
        video = media_defaults(self.style, role="evidence", asset_type="video")
        self.assertEqual(image["transition"], "hard_cut")
        self.assertEqual(image["treatment"], "highlight_crop")
        self.assertEqual(video["treatment"], "natural_motion")

    def test_invalid_role_duration_fails_closed(self):
        broken = copy.deepcopy(self.style)
        broken["visual_roles"]["evidence"]["duration_seconds"] = {
            "min": 8,
            "preferred": 4,
            "max": 6,
        }
        with self.assertRaisesRegex(ValueError, "min <= preferred <= max"):
            validate_editing_style(broken)

    def test_lint_detects_late_presenter_and_long_opening_media_run(self):
        timeline = [
            {
                "segment_id": "seg_001",
                "mode": "media",
                "start_seconds": 0,
                "end_seconds": 20,
                "duration_seconds": 20,
                "director": {
                    "visual_role": "rhythm",
                    "transition_in": "hard_cut",
                    "transition_out": "hard_cut",
                },
            },
            {
                "segment_id": "seg_002",
                "mode": "presenter",
                "start_seconds": 20,
                "end_seconds": 60,
                "duration_seconds": 40,
                "director": {
                    "visual_role": "presenter",
                    "transition_in": "hard_cut",
                    "transition_out": "none",
                },
            },
        ]
        warnings = lint_timeline(timeline, self.style, duration_seconds=60)
        codes = {item["code"] for item in warnings}
        self.assertIn("opening_presenter_anchor_late", codes)
        self.assertIn("continuous_media_too_long", codes)

    def test_lint_allows_early_presenter_then_dense_opening(self):
        timeline = [
            {
                "segment_id": "seg_001",
                "mode": "presenter",
                "start_seconds": 0,
                "end_seconds": 3.5,
                "duration_seconds": 3.5,
                "director": {
                    "visual_role": "presenter",
                    "transition_in": "none",
                    "transition_out": "none",
                },
            },
            {
                "segment_id": "seg_002",
                "mode": "media",
                "start_seconds": 3.5,
                "end_seconds": 7,
                "duration_seconds": 3.5,
                "director": {
                    "visual_role": "rhythm",
                    "transition_in": "hard_cut",
                    "transition_out": "hard_cut",
                },
            },
            {
                "segment_id": "seg_003",
                "mode": "media",
                "start_seconds": 7,
                "end_seconds": 10.5,
                "duration_seconds": 3.5,
                "director": {
                    "visual_role": "rhythm",
                    "transition_in": "hard_cut",
                    "transition_out": "hard_cut",
                },
            },
            {
                "segment_id": "seg_004",
                "mode": "presenter",
                "start_seconds": 10.5,
                "end_seconds": 30,
                "duration_seconds": 19.5,
                "director": {
                    "visual_role": "presenter",
                    "transition_in": "hard_cut",
                    "transition_out": "none",
                },
            },
        ]
        warnings = lint_timeline(timeline, self.style, duration_seconds=30)
        codes = {item["code"] for item in warnings}
        self.assertNotIn("opening_presenter_anchor_late", codes)
        self.assertNotIn("continuous_media_too_long", codes)



    def test_split_timeline_fragments_are_linted_as_one_media_cue(self):
        timeline = [
            {
                "segment_id": "seg_001",
                "cue_id": "slot_001",
                "mode": "media",
                "start_seconds": 10,
                "end_seconds": 12,
                "duration_seconds": 2,
                "director": {
                    "visual_role": "evidence",
                    "transition_in": "hard_cut",
                    "transition_out": "hard_cut",
                },
            },
            {
                "segment_id": "seg_002",
                "cue_id": "slot_001",
                "mode": "media",
                "start_seconds": 12,
                "end_seconds": 16,
                "duration_seconds": 4,
                "director": {
                    "visual_role": "evidence",
                    "transition_in": "hard_cut",
                    "transition_out": "hard_cut",
                },
            },
            {
                "segment_id": "seg_003",
                "mode": "presenter",
                "start_seconds": 16,
                "end_seconds": 30,
                "duration_seconds": 14,
                "director": {
                    "visual_role": "presenter",
                    "transition_in": "hard_cut",
                    "transition_out": "none",
                },
            },
        ]
        warnings = lint_timeline(timeline, self.style, duration_seconds=30)
        short = [item for item in warnings if item["code"] == "media_segment_short"]
        self.assertEqual(short, [])


    def test_real_pre_style_replay_exposes_opening_regressions(self):
        payload = json.loads(REAL_EDIT_REPLAY.read_text(encoding="utf-8"))
        warnings = lint_timeline(
            payload["timeline"],
            self.style,
            duration_seconds=payload["timing"]["duration_seconds"],
        )
        codes = {item["code"] for item in warnings}
        self.assertIn("opening_presenter_anchor_late", codes)
        self.assertIn("continuous_media_too_long", codes)
        self.assertIn("presenter_share_high", codes)


    def test_yaml_loader_rejects_non_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "style.yaml"
            path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must contain a mapping"):
                load_editing_style(path)


if __name__ == "__main__":
    unittest.main()
