from __future__ import annotations

import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import yaml

from pipeline.news_ingestion_followup import dispatch_checks
from test_staged_news_issue import digest

ROOT = Path(__file__).resolve().parents[1]


class NewsIngestionFollowupTests(unittest.TestCase):
    @patch("pipeline.news_ingestion_followup.subprocess.run")
    def test_dispatches_recovered_day_and_its_original_production_window(self, run):
        with tempfile.TemporaryDirectory() as tmp:
            news = Path(tmp)
            day = date(2026, 9, 30)
            (news / "2026-09-30-18-54-17.txt").write_text(
                digest("2026-09-30 18:54:17", item_date="2026-09-30"), encoding="utf-8"
            )
            dispatch_checks(day, "jcval94/AI-News-Daily", news, as_of=date(2026, 10, 3))
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[0][3], "news-ingestion-watchdog.yml")
        self.assertEqual(commands[0][-1], "date=2026-09-30")
        self.assertEqual(commands[1][3], "production-preflight.yml")
        self.assertEqual(commands[1][-1], "target_date=2026-10-02")
        self.assertTrue(all(call.kwargs["check"] for call in run.call_args_list))

    @patch("pipeline.news_ingestion_followup.subprocess.run")
    def test_future_window_is_not_reported_as_failed_before_its_last_source_day(self, run):
        with tempfile.TemporaryDirectory() as tmp:
            news = Path(tmp)
            (news / "2026-10-03-08-00-00.txt").write_text(
                digest("2026-10-03 08:00:00", item_date="2026-10-03"), encoding="utf-8"
            )
            dispatch_checks(date(2026, 10, 3), "jcval94/AI-News-Daily", news, as_of=date(2026, 10, 3))
            self.assertEqual(run.call_count, 1)
            run.reset_mock()
            dispatch_checks(date(2026, 10, 3), "jcval94/AI-News-Daily", news, as_of=date(2026, 10, 5))
            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args.args[0][-1], "target_date=2026-10-06")

    @patch("pipeline.news_ingestion_followup.subprocess.run")
    def test_missing_or_thin_digest_never_dispatches(self, run):
        with tempfile.TemporaryDirectory() as tmp:
            news = Path(tmp)
            day = date(2026, 9, 29)
            with self.assertRaisesRegex(ValueError, "unhealthy"):
                dispatch_checks(day, "jcval94/AI-News-Daily", news)
            body = digest("2026-09-29 08:00:00", item_date="2026-09-29")
            thin = body.split("Título: Caso current 2", 1)[0]
            (news / "2026-09-29-08-00-00.txt").write_text(thin, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unhealthy"):
                dispatch_checks(day, "jcval94/AI-News-Daily", news)
        run.assert_not_called()

    @patch("pipeline.news_ingestion_followup.subprocess.run")
    def test_dispatch_failure_propagates_for_handoff_retry(self, run):
        run.side_effect = subprocess.CalledProcessError(1, "gh")
        with tempfile.TemporaryDirectory() as tmp:
            news = Path(tmp)
            (news / "2026-10-03-08-00-00.txt").write_text(
                digest("2026-10-03 08:00:00", item_date="2026-10-03"), encoding="utf-8"
            )
            with self.assertRaises(subprocess.CalledProcessError):
                dispatch_checks(date(2026, 10, 3), "jcval94/AI-News-Daily", news)
        self.assertEqual(run.call_count, 1)

    def test_idle_bridge_cannot_dispatch_and_acknowledgement_follows_checks(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/gdrive-raw-bridge-probe.yml").read_text())
        steps = workflow["jobs"]["consume"]["steps"]
        names = [step["name"] for step in steps]
        refresh = steps[names.index("Refresh ingestion health and production readiness")]
        self.assertIn("steps.select.outputs.file_id != ''", refresh["if"])
        self.assertIn("steps.validate.outcome == 'success'", refresh["if"])
        self.assertLess(names.index(refresh["name"]), names.index("Move consumed handoff to processed"))


if __name__ == "__main__":
    unittest.main()
