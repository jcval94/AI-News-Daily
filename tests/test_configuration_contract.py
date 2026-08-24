from __future__ import annotations

import unittest
from pathlib import Path

from pipeline.core import PIPELINE_ENV_DEFAULTS


class ConfigurationContractTests(unittest.TestCase):
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
