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



if __name__ == "__main__":
    unittest.main()
