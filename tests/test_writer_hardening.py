from __future__ import annotations

import unittest
from types import SimpleNamespace

from pipeline.writer_hardening import MARKER_GUARD, hardened_writer_agent, install


class WriterHardeningTests(unittest.TestCase):
    def test_marker_guard_forbids_duplicate_or_second_pass_markers(self) -> None:
        self.assertIn("appears exactly once", MARKER_GUARD)
        self.assertIn("No beat marker may be repeated", MARKER_GUARD)
        self.assertIn("len(episode_plan.beats) + 2", MARKER_GUARD)
        self.assertIn("Return one draft only", MARKER_GUARD)

    def test_install_replaces_only_writer_reference(self) -> None:
        original = object()
        base = SimpleNamespace(writer_agent=original, another_agent=original)
        installed = install(base)
        self.assertIs(installed.writer_agent, hardened_writer_agent)
        self.assertIs(installed.another_agent, original)


if __name__ == "__main__":
    unittest.main()
