from __future__ import annotations

import unittest
from pathlib import Path


class ReviewHubWorkflowContractTests(unittest.TestCase):
    def test_non_publishable_build_states_are_graceful_noops(self) -> None:
        workflow = Path(".github/workflows/editorial-review-hub.yml").read_text(encoding="utf-8")
        self.assertIn("skip_review_hub: ${{ steps.source.outputs.skip_review_hub }}", workflow)
        self.assertIn(
            "no_source_news|no_relevant_news|no_novel_essay_angle|missing_openai_secret)",
            workflow,
        )
        self.assertIn('echo "skip_review_hub=true" >> "$GITHUB_OUTPUT"', workflow)
        self.assertIn("if: steps.source.outputs.skip_review_hub != 'true'", workflow)
        self.assertIn(
            "if: needs.build.outputs.skip_review_hub != 'true' && needs.build.outputs.source_head_branch == 'main'",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
