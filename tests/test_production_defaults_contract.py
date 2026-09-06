from __future__ import annotations

import json
import unittest
from pathlib import Path


class ProductionDefaultsContractTests(unittest.TestCase):
    def test_production_defaults_match_workflow_policy(self) -> None:
        defaults = json.loads(Path("config/production_defaults.json").read_text(encoding="utf-8"))
        workflow = Path(".github/workflows/build-video-kit.yml").read_text(encoding="utf-8")
        self.assertIn(
            f"MAX_MEDIA: ${{{{ vars.MAX_MEDIA_DOWNLOADS || '{defaults['MAX_MEDIA_DOWNLOADS']}' }}}}",
            workflow,
        )
        self.assertIn(
            f"MEDIA_MIN_RELEVANCE_SCORE: ${{{{ vars.MEDIA_MIN_RELEVANCE_SCORE || '{defaults['MEDIA_MIN_RELEVANCE_SCORE']}' }}}}",
            workflow,
        )
        self.assertIn(
            f"MIN_SOURCE_COVERAGE_RATIO: ${{{{ vars.MIN_SOURCE_COVERAGE_RATIO || '{defaults['MIN_SOURCE_COVERAGE_RATIO']}' }}}}",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
