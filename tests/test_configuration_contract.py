from __future__ import annotations

import unittest
from pathlib import Path

from pipeline.core import PIPELINE_ENV_DEFAULTS


class ConfigurationContractTests(unittest.TestCase):
    def test_production_workflow_fails_every_non_publishable_terminal_state(self) -> None:
        workflow = Path(".github/workflows/build-video-kit.yml").read_text(encoding="utf-8")
        for status in (
            "missing_openai_secret",
            "no_source_news",
            "no_relevant_news",
            "no_novel_essay_angle",
            "failure",
            "script_not_approved",
        ):
            self.assertIn(
                f"steps.episode_outcome.outputs.status == '{status}'",
                workflow,
                status,
            )

    def test_editorial_regression_uses_semantic_latest_source_date(self) -> None:
        workflow = Path(".github/workflows/editorial-regression.yml").read_text(encoding="utf-8")
        self.assertIn("latest_source_date", workflow)
        self.assertIn("pipeline.source_naming", workflow)
        self.assertNotIn("-name '????-??-??.txt'", workflow)

    def test_python_floor_matches_ci_runtime(self) -> None:
        pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('requires-python = ">=3.12"', pyproject)
        for path in Path(".github/workflows").glob("*.yml"):
            workflow = path.read_text(encoding="utf-8")
            if "actions/setup-python@" in workflow and "python-version:" in workflow:
                self.assertNotIn('python-version: "3.11"', workflow, path.name)

    def test_every_pipeline_env_is_exposed_to_build_and_report(self) -> None:
        workflow = Path(".github/workflows/build-video-kit.yml").read_text(encoding="utf-8")
        for name in PIPELINE_ENV_DEFAULTS:
            if name == "MAX_MEDIA_DOWNLOADS":
                # The script/judge runtime intentionally receives zero media so it does not
                # pay for the legacy sparse planner. The real configurable budget belongs to
                # the dedicated dense-media stage and is then exposed again to the run report.
                self.assertIn("--max-media-downloads 0", workflow)
                self.assertIn("MAX_MEDIA: ${{ vars.MAX_MEDIA_DOWNLOADS || '54' }}", workflow)
                self.assertIn("MAX_MEDIA_DOWNLOADS: ${{ vars.MAX_MEDIA_DOWNLOADS || '54' }}", workflow)
                continue
            self.assertGreaterEqual(workflow.count(f"{name}:"), 2, name)


if __name__ == "__main__":
    unittest.main()
