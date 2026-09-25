from pathlib import Path
import unittest


class ProductionHandoffHardeningTests(unittest.TestCase):
    def test_backfill_reaches_same_post_approval_handoff(self) -> None:
        workflow = Path(".github/workflows/backfill-video-kit.yml").read_text(encoding="utf-8")
        for command in (
            "pipeline.review_media_offline_dense",
            "pipeline.production_script",
            "pipeline.recording_pack",
            "pipeline.virtual_timeline",
            "pipeline.placeholder_media",
            "pipeline.resolve_bridge",
            "pipeline.otio_export",
            "pipeline.report",
        ):
            self.assertIn(command, workflow)
        self.assertIn('git add "scripts/$TARGET_DATE" "multimedia/$TARGET_DATE"', workflow)

    def test_review_hub_has_canonical_fallback_when_artifacts_expire(self) -> None:
        workflow = Path(".github/workflows/editorial-review-hub.yml").read_text(encoding="utf-8")
        self.assertIn("falling back to canonical repository history", workflow)
        self.assertIn("--root scripts", workflow)
        self.assertIn('SELECTED_RUN_ID="canonical"', workflow)
        self.assertIn('SELECTED_ARTIFACT_NAME="canonical-repository"', workflow)

    def test_production_preflight_imports_local_editing_bridge_modules(self) -> None:
        workflow = Path(".github/workflows/build-video-kit.yml").read_text(encoding="utf-8")
        self.assertIn("pipeline.placeholder_media", workflow)
        self.assertIn("pipeline.resolve_bridge", workflow)

    def test_report_contract_lists_modern_handoff_artifacts(self) -> None:
        source = Path("pipeline/report.py").read_text(encoding="utf-8")
        for key in (
            '"recording_pack"',
            '"virtual_timeline"',
            '"timeline_otio"',
            '"placeholder_manifest"',
            '"resolve_bridge_plan"',
        ):
            self.assertIn(key, source)


if __name__ == "__main__":
    unittest.main()
