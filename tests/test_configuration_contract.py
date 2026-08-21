from __future__ import annotations

import unittest
from pathlib import Path

from pipeline.core import PIPELINE_ENV_DEFAULTS


class ConfigurationContractTests(unittest.TestCase):
    def test_every_pipeline_env_is_exposed_to_build_and_report(self) -> None:
        workflow = Path(".github/workflows/build-video-kit.yml").read_text(encoding="utf-8")
        for name in PIPELINE_ENV_DEFAULTS:
            self.assertGreaterEqual(workflow.count(f"{name}:"), 2, name)


if __name__ == "__main__":
    unittest.main()
