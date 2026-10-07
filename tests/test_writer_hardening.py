from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.agent import WriterDraftResult
from pipeline.writer_hardening import MARKER_GUARD, hardened_writer_agent, install


class WriterHardeningTests(unittest.TestCase):
    def test_writer_guard_requires_structured_sections_and_no_markers(self) -> None:
        self.assertIn("beats contains exactly one spoken string", MARKER_GUARD)
        self.assertIn("Do not emit <!--SECTION:...-->", MARKER_GUARD)
        self.assertIn("primary_memory_section_index", MARKER_GUARD)
        self.assertIn("primary Narrative Memory passage must BEGIN", MARKER_GUARD)
        self.assertIn("Return one structured draft only", MARKER_GUARD)
        self.assertIs(hardened_writer_agent.output_schema, WriterDraftResult)
        self.assertEqual(hardened_writer_agent.output_key, "writer_draft")

    def test_install_replaces_only_writer_reference(self) -> None:
        original = object()
        base = SimpleNamespace(writer_agent=original, another_agent=original)
        installed = install(base)
        self.assertIs(installed.writer_agent, hardened_writer_agent)
        self.assertIs(installed.another_agent, original)


if __name__ == "__main__":
    unittest.main()
