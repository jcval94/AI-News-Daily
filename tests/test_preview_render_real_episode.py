import json
import tempfile
import unittest
from pathlib import Path

from pipeline.placeholder_media import build_placeholder_manifest
from pipeline.preview_render import build_preview_plan
from pipeline.resolve_bridge import build_resolve_plan


ROOT = Path(__file__).resolve().parents[1]
REAL_VIRTUAL = (
    ROOT
    / "docs"
    / "examples"
    / "virtual_timeline"
    / "2026-09-04"
    / "virtual_timeline.json"
)


class RealPreviewReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.virtual = json.loads(REAL_VIRTUAL.read_text(encoding="utf-8"))

    def test_real_episode_flattens_to_contiguous_visual_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            episode = repo_root / "scripts" / "2026-09-04"
            placeholders = episode / "placeholder_media"
            placeholders.mkdir(parents=True)
            manifest = build_placeholder_manifest(
                virtual_timeline=self.virtual,
                output_dir=placeholders,
                width=640,
                height=360,
            )
            resolve_plan = build_resolve_plan(
                virtual_timeline=self.virtual,
                placeholder_manifest=manifest,
                repo_root=repo_root,
            )
            preview = build_preview_plan(
                resolve_plan=resolve_plan,
                repo_root=repo_root,
            )

            self.assertAlmostEqual(preview["summary"]["duration_seconds"], 917.6, places=1)
            self.assertGreater(preview["summary"]["segment_count"], 25)
            self.assertFalse(preview["policy"]["publishable"])
            self.assertFalse(preview["policy"]["frame_accurate"])
            self.assertTrue(preview["policy"]["requires_recording_retime"])

            expected_broll = sum(
                float(item["duration_seconds"])
                for item in resolve_plan["placements"]
                if item["track_id"] == "V2"
            )
            self.assertAlmostEqual(
                preview["summary"]["broll_seconds"],
                expected_broll,
                places=2,
            )
            self.assertAlmostEqual(
                preview["summary"]["placeholder_broll_seconds"],
                expected_broll,
                places=2,
            )
            self.assertEqual(preview["summary"]["resolved_broll_seconds"], 0.0)

            cursor = 0.0
            for segment in preview["segments"]:
                self.assertAlmostEqual(segment["timeline_start_seconds"], cursor, places=2)
                self.assertGreater(segment["duration_seconds"], 0)
                cursor = segment["timeline_end_seconds"]
            self.assertAlmostEqual(cursor, 917.6, places=1)

    def test_real_preview_uses_v2_where_media_cues_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            placeholders = repo_root / "scripts" / "2026-09-04" / "placeholder_media"
            placeholders.mkdir(parents=True)
            manifest = build_placeholder_manifest(
                virtual_timeline=self.virtual,
                output_dir=placeholders,
                width=640,
                height=360,
            )
            resolve_plan = build_resolve_plan(
                virtual_timeline=self.virtual,
                placeholder_manifest=manifest,
                repo_root=repo_root,
            )
            preview = build_preview_plan(
                resolve_plan=resolve_plan,
                repo_root=repo_root,
            )
            preview_v2_ids = {
                item["placement_id"] for item in preview["segments"] if item["track_id"] == "V2"
            }
            resolve_v2_ids = {
                item["placement_id"] for item in resolve_plan["placements"] if item["track_id"] == "V2"
            }
            self.assertEqual(preview_v2_ids, resolve_v2_ids)


if __name__ == "__main__":
    unittest.main()
