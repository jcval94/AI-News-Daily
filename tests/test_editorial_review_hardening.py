from __future__ import annotations

import unittest
from types import SimpleNamespace

from pipeline.editorial_review_hardening import (
    HARDENED_REVIEWER_INSTRUCTION,
    hardened_reviewer_agent,
    install,
)


class EditorialReviewHardeningTests(unittest.TestCase):
    def test_instruction_puts_script_in_explicit_primary_block(self) -> None:
        self.assertIn("<SCRIPT>\n{draft_script}\n</SCRIPT>", HARDENED_REVIEWER_INSTRUCTION)
        self.assertIn("<SELECTED_CURRENT_NEWS>\n{selected_news}\n</SELECTED_CURRENT_NEWS>", HARDENED_REVIEWER_INSTRUCTION)
        self.assertNotIn("{news_text}", HARDENED_REVIEWER_INSTRUCTION)
        self.assertIn("why_it_matters", HARDENED_REVIEWER_INSTRUCTION)
        self.assertIn("MUST NOT be treated as factual proof", HARDENED_REVIEWER_INSTRUCTION)

    def test_production_reviewer_receives_exact_selected_memory_and_publisher_excerpts(self) -> None:
        prompt = HARDENED_REVIEWER_INSTRUCTION
        self.assertIn("<SELECTED_NARRATIVE_MEMORY>\n{selected_narrative_memory}\n</SELECTED_NARRATIVE_MEMORY>", prompt)
        self.assertIn("<PUBLISHER_EXCERPTS>\n{source_evidence}\n</PUBLISHER_EXCERPTS>", prompt)
        self.assertIn("verified_claims", prompt)
        self.assertIn("uncertainties and analogy_limits", prompt)
        self.assertIn("Missing excerpts are not disproof", prompt)
        self.assertIn("require low factuality risk", prompt)

    def test_install_replaces_only_reviewer_reference(self) -> None:
        original = object()
        base = SimpleNamespace(reviewer_agent=original, another_agent=original)
        installed = install(base)
        self.assertIs(installed.reviewer_agent, hardened_reviewer_agent)
        self.assertIs(installed.another_agent, original)


if __name__ == "__main__":
    unittest.main()
