from pathlib import Path
import unittest


class ProductionHandoffHardeningTests(unittest.TestCase):
    def test_backfill_reaches_same_post_approval_handoff(self) -> None:
        workflow = Path(".github/workflows/backfill-video-kit.yml").read_text(encoding="utf-8")
        for command in (
            "pipeline.review_media_offline_dense",
            "pipeline.production_script",
            "pipeline.recording_pack",
            "pipeline.recording_ingest",
            "pipeline.recording_alignment",
            "pipeline.virtual_timeline",
            "pipeline.placeholder_media",
            "pipeline.resolve_bridge",
            "pipeline.preview_render",
            "pipeline.asset_readiness",
            "pipeline.otio_export",
            "pipeline.report",
        ):
            self.assertIn(command, workflow)
        self.assertIn('git add "scripts/$TARGET_DATE" "multimedia/$TARGET_DATE"', workflow)


    def test_backfill_exposes_configured_media_provider_to_dense_builder(self) -> None:
        workflow = Path(".github/workflows/backfill-video-kit.yml").read_text(encoding="utf-8")
        handoff = workflow.split("- name: Build deterministic dense multimedia handoff", 1)[1].split(
            "- name: Create production handoff contracts", 1
        )[0]
        self.assertIn("PEXELS_API_KEY:", handoff)
        self.assertIn("MEDIA_HTTP_MAX_ATTEMPTS:", handoff)
        self.assertIn("MEDIA_HTTP_RETRY_BASE_SECONDS:", handoff)

    def test_dense_media_gate_is_shared_and_dedup_aware(self) -> None:
        for path in (
            ".github/workflows/build-video-kit.yml",
            ".github/workflows/backfill-video-kit.yml",
        ):
            workflow = Path(path).read_text(encoding="utf-8")
            self.assertIn("pipeline.media_density_gate", workflow)
            self.assertNotIn("expected >=45 assets", workflow)

    def test_backfill_reuses_only_complete_approved_editorial_diagnostics(self) -> None:
        workflow = Path(".github/workflows/backfill-video-kit.yml").read_text(encoding="utf-8")
        self.assertIn("actions: read", workflow)
        self.assertIn("Restore approved editorial artifact from recent diagnostic", workflow)
        self.assertIn("if: steps.reuse.outputs.restored != 'true'", workflow)
        for required in (
            "run_state.json",
            "script.txt",
            "episode_plan.json",
            "selected_news.json",
            "script_sections.json",
            "run_report.json",
        ):
            self.assertIn(required, workflow)
        self.assertIn('STATUS" != "approved"', workflow)
        self.assertIn('EPISODE_DATE" != "$TARGET_DATE"', workflow)

    def test_failed_backfill_preserves_latest_isolated_workspace(self) -> None:
        workflow = Path(".github/workflows/backfill-video-kit.yml").read_text(encoding="utf-8")
        self.assertIn("Preserve failed backfill recovery workspace", workflow)
        self.assertIn("ai-news-backfill-recovery-", workflow)
        self.assertIn("if: failure() && steps.workspace.outputs.run_root != ''", workflow)

    def test_otio_is_built_before_resolve_bridge_in_main_and_backfill(self) -> None:
        for path in (
            ".github/workflows/build-video-kit.yml",
            ".github/workflows/backfill-video-kit.yml",
        ):
            workflow = Path(path).read_text(encoding="utf-8")
            otio = workflow.index("python -m pipeline.otio_export")
            resolve = workflow.index("python -m pipeline.resolve_bridge")
            self.assertLess(otio, resolve, path)


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
        self.assertIn("pipeline.preview_render", workflow)
        self.assertIn("pipeline.asset_readiness", workflow)
        self.assertIn("pipeline.recording_ingest", workflow)
        self.assertIn("pipeline.recording_alignment", workflow)
        self.assertIn("pipeline.resolve_alignment_bridge", workflow)
        self.assertIn("pipeline.whisperx_adapter", workflow)


    def test_video_workflows_install_ffmpeg_before_preview(self) -> None:
        for path in (
            ".github/workflows/build-video-kit.yml",
            ".github/workflows/backfill-video-kit.yml",
        ):
            workflow = Path(path).read_text(encoding="utf-8")
            install = workflow.index("sudo apt-get update -qq && sudo apt-get install -y ffmpeg")
            preview = workflow.index("python -m pipeline.preview_render")
            self.assertLess(install, preview, path)
            self.assertIn("command -v ffmpeg >/dev/null", workflow)
            self.assertIn("command -v ffprobe >/dev/null", workflow)

    def test_preview_mp4_stays_in_isolated_run_artifact(self) -> None:
        workflow = Path(".github/workflows/build-video-kit.yml").read_text(encoding="utf-8")
        self.assertIn(
            '$RUN_ROOT/previews/$TARGET_DATE/pre_recording_preview.mp4',
            workflow,
        )
        promote = workflow.split("- name: Promote approved episode", 1)[1].split("- name: Commit approved canonical artifacts", 1)[0]
        self.assertNotIn('"previews/$TARGET_DATE"', promote)

    def test_raw_recordings_are_gitignored(self) -> None:
        ignored = Path(".gitignore").read_text(encoding="utf-8")
        self.assertIn("recordings/", ignored)

    def test_report_contract_lists_modern_handoff_artifacts(self) -> None:
        source = Path("pipeline/report.py").read_text(encoding="utf-8")
        for key in (
            '"recording_pack"',
            '"recording_ingest_contract"',
            '"recording_ingest_instructions"',
            '"recording_ingest_manifest"',
            '"recording_alignment_contract"',
            '"recording_alignment"',
            '"resolve_alignment_plan"',
            '"resolve_alignment_execution"',
            '"virtual_timeline"',
            '"timeline_otio"',
            '"placeholder_manifest"',
            '"resolve_bridge_plan"',
            '"pre_recording_preview_plan"',
            '"pre_recording_preview_validation"',
            '"asset_readiness"',
            '"asset_readiness_html"',
        ):
            self.assertIn(key, source)


if __name__ == "__main__":
    unittest.main()
