import json
import tempfile
import unittest
from pathlib import Path

import yaml

from pipeline.asset_readiness import build_asset_readiness
from pipeline.placeholder_media import build_placeholder_manifest
from pipeline.resolve_bridge import build_resolve_plan


ROOT = Path(__file__).resolve().parents[1]
REAL_VIRTUAL = (
    ROOT / "docs" / "examples" / "virtual_timeline" / "2026-09-04" / "virtual_timeline.json"
)
POLICY_PATH = ROOT / "config" / "asset_readiness.yaml"


class RealAssetReadinessReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.virtual = json.loads(REAL_VIRTUAL.read_text(encoding="utf-8"))
        cls.policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))

    def test_historical_episode_is_honestly_blocked_until_assets_resolve(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            placeholders = root / "scripts" / "2026-09-04" / "placeholder_media"
            placeholders.mkdir(parents=True)
            manifest = build_placeholder_manifest(
                virtual_timeline=self.virtual,
                output_dir=placeholders,
                width=640,
                height=360,
            )
            resolve = build_resolve_plan(
                virtual_timeline=self.virtual,
                placeholder_manifest=manifest,
                repo_root=root,
            )
            result = build_asset_readiness(
                virtual_timeline=self.virtual,
                resolve_plan=resolve,
                preview_validation=None,
                repo_root=root,
                policy=self.policy,
            )
            self.assertFalse(result["gate"]["ready_to_record"])
            self.assertEqual(result["status"], "blocked_before_recording")
            self.assertEqual(result["summary"]["planned_cue_count"], 15)
            self.assertEqual(result["summary"]["resolved_cue_count"], 0)
            self.assertEqual(result["summary"]["missing_cue_count"], 15)
            self.assertEqual(result["summary"]["resolved_cue_ratio"], 0.0)
            self.assertEqual(result["summary"]["resolved_visual_seconds_ratio"], 0.0)
            self.assertIn(
                "resolved_cue_ratio_below_threshold",
                result["gate"]["blockers"],
            )
            self.assertIn(
                "resolved_visual_seconds_ratio_below_threshold",
                result["gate"]["blockers"],
            )


if __name__ == "__main__":
    unittest.main()
