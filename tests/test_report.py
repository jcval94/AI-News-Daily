from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from pipeline.report import build_report


class ReportTests(unittest.TestCase):
    def test_report_uses_run_state_and_hashes_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            news = root / "news"
            scripts = root / "scripts"
            multimedia = root / "multimedia"
            news.mkdir()
            episode_dir = scripts / "2026-08-21"
            episode_dir.mkdir(parents=True)
            (news / "2026-08-20.txt").write_text("Fuente: test\nEnlace: https://example.com\n" * 20, encoding="utf-8")
            (episode_dir / "run_state.json").write_text(
                json.dumps({"status": "no_relevant_news", "reason": "nothing strong"}),
                encoding="utf-8",
            )
            (episode_dir / "execution_trace.json").write_text(
                json.dumps({"agent_calls": [], "refinement_iterations": []}),
                encoding="utf-8",
            )
            report = build_report(date(2026, 8, 21), news, scripts, multimedia, "no_relevant_news")
            self.assertEqual(report["status"], "no_relevant_news")
            self.assertEqual(report["source_window"]["available_files"][0]["name"], "2026-08-20.txt")
            self.assertTrue(report["source_window"]["available_files"][0]["sha256"])
            self.assertTrue(report["artifacts"]["run_state"]["sha256"])


if __name__ == "__main__":
    unittest.main()
