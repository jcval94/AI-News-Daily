from pathlib import Path
import unittest


class PromotionGuardTests(unittest.TestCase):
    def test_production_script_must_succeed_before_promotion(self) -> None:
        workflow = Path(".github/workflows/build-video-kit.yml").read_text(encoding="utf-8")
        required = "steps.production_script.outcome == 'success'"
        self.assertGreaterEqual(workflow.count(required), 2)

        refresh = workflow.split("- name: Refresh branch before promotion", 1)[1].split("- name: Promote approved episode", 1)[0]
        promote = workflow.split("- name: Promote approved episode", 1)[1].split("- name: Commit approved canonical artifacts", 1)[0]
        self.assertIn(required, refresh)
        self.assertIn(required, promote)



    def test_recording_ingest_contract_must_succeed_before_promotion(self) -> None:
        workflow = Path(".github/workflows/build-video-kit.yml").read_text(encoding="utf-8")
        required = "steps.recording_ingest_contract.outcome == 'success'"
        self.assertGreaterEqual(workflow.count(required), 2)
        self.assertIn("steps.recording_ingest_contract.outcome == 'failure'", workflow)

    def test_virtual_timeline_must_succeed_before_promotion(self) -> None:
        workflow = Path(".github/workflows/build-video-kit.yml").read_text(encoding="utf-8")
        required = "steps.virtual_timeline.outcome == 'success'"
        self.assertGreaterEqual(workflow.count(required), 2)

        refresh = workflow.split("- name: Refresh branch before promotion", 1)[1].split("- name: Promote approved episode", 1)[0]
        promote = workflow.split("- name: Promote approved episode", 1)[1].split("- name: Commit approved canonical artifacts", 1)[0]
        self.assertIn(required, refresh)
        self.assertIn(required, promote)
        self.assertIn("steps.virtual_timeline.outcome == 'failure'", workflow)



    def test_otio_export_must_succeed_before_promotion(self) -> None:
        workflow = Path(".github/workflows/build-video-kit.yml").read_text(encoding="utf-8")
        required = "steps.otio_export.outcome == 'success'"
        self.assertGreaterEqual(workflow.count(required), 2)

        refresh = workflow.split("- name: Refresh branch before promotion", 1)[1].split("- name: Promote approved episode", 1)[0]
        promote = workflow.split("- name: Promote approved episode", 1)[1].split("- name: Commit approved canonical artifacts", 1)[0]
        self.assertIn(required, refresh)
        self.assertIn(required, promote)
        self.assertIn("steps.otio_export.outcome == 'failure'", workflow)



    def test_placeholder_and_resolve_plan_must_succeed_before_promotion(self) -> None:
        workflow = Path(".github/workflows/build-video-kit.yml").read_text(encoding="utf-8")
        for required in (
            "steps.placeholder_media.outcome == 'success'",
            "steps.resolve_bridge.outcome == 'success'",
        ):
            self.assertGreaterEqual(workflow.count(required), 2)
            self.assertIn(required.replace("== 'success'", "== 'failure'"), workflow)


    def test_pre_recording_preview_must_succeed_before_promotion(self) -> None:
        workflow = Path(".github/workflows/build-video-kit.yml").read_text(encoding="utf-8")
        required = "steps.pre_recording_preview.outcome == 'success'"
        self.assertGreaterEqual(workflow.count(required), 2)

        refresh = workflow.split("- name: Refresh branch before promotion", 1)[1].split("- name: Promote approved episode", 1)[0]
        promote = workflow.split("- name: Promote approved episode", 1)[1].split("- name: Commit approved canonical artifacts", 1)[0]
        self.assertIn(required, refresh)
        self.assertIn(required, promote)
        self.assertIn("steps.pre_recording_preview.outcome == 'failure'", workflow)


    def test_asset_readiness_must_succeed_before_promotion(self) -> None:
        workflow = Path(".github/workflows/build-video-kit.yml").read_text(encoding="utf-8")
        required = "steps.asset_readiness.outcome == 'success'"
        self.assertGreaterEqual(workflow.count(required), 2)
        self.assertIn("steps.asset_readiness.outcome == 'failure'", workflow)
        self.assertIn("--enforce", workflow)

    def test_script_only_manual_run_cannot_promote_canonical_episode(self) -> None:
        workflow = Path(".github/workflows/build-video-kit.yml").read_text(encoding="utf-8")
        self.assertIn(
            'Canonical promotion requires download_multimedia=true',
            workflow,
        )
        self.assertIn(
            '[ "$PROMOTE_APPROVED" = "true" ] && [ "$DOWNLOAD_MULTIMEDIA" != "true" ]',
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
