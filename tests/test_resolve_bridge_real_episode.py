import json
import tempfile
import unittest
from pathlib import Path

from pipeline.placeholder_media import build_placeholder_manifest
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


class RealResolveBridgeReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.virtual = json.loads(REAL_VIRTUAL.read_text(encoding="utf-8"))

    def test_real_episode_materializes_complete_pre_recording_resolve_plan(self):
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
            plan = build_resolve_plan(
                virtual_timeline=self.virtual,
                placeholder_manifest=manifest,
                repo_root=repo_root,
            )

            self.assertEqual(manifest["summary"]["presenter_placeholder_count"], 25)
            self.assertEqual(manifest["summary"]["media_placeholder_count"], 15)
            self.assertEqual(manifest["summary"]["placeholder_count"], 40)

            self.assertTrue(plan["readiness"]["plan_valid"])
            self.assertTrue(plan["readiness"]["ready_for_resolve_execution"])
            self.assertFalse(plan["readiness"]["final_edit_ready"])
            self.assertEqual(plan["summary"]["import_count"], 40)
            self.assertEqual(plan["summary"]["placement_count"], 40)
            self.assertEqual(plan["summary"]["presenter_placeholder_count"], 25)
            self.assertEqual(plan["summary"]["broll_count"], 15)
            self.assertEqual(plan["summary"]["broll_placeholder_count"], 15)
            self.assertEqual(plan["summary"]["marker_count"], 36)
            self.assertAlmostEqual(plan["summary"]["duration_seconds"], 917.6, places=1)

            v1 = [item for item in plan["placements"] if item["track_id"] == "V1"]
            v2 = [item for item in plan["placements"] if item["track_id"] == "V2"]
            self.assertEqual(v1[0]["take_id"], "opening_t01")
            self.assertEqual(v1[-1]["take_id"], "cta_t01")
            self.assertEqual(v2[0]["cue_id"], "slot_001")
            self.assertTrue(all(item["placeholder"] for item in v1 + v2))

    def test_real_plan_still_declares_real_a_roll_as_final_blocker(self):
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
            plan = build_resolve_plan(
                virtual_timeline=self.virtual,
                placeholder_manifest=manifest,
                repo_root=repo_root,
            )
            self.assertIn("real_a_roll_not_ingested", plan["readiness"]["blockers"])


if __name__ == "__main__":
    unittest.main()
