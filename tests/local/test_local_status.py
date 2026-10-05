import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pipeline.local.status import build_status
from pipeline.schema_validation import validate_payload


class LocalStatusTests(unittest.TestCase):
    def test_status_counts_private_and_repo_state_without_absolute_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "local_handoff" / "requests").mkdir(parents=True)
            (root / "local_handoff" / "requests" / "job.json").write_text("{}", encoding="utf-8")
            staged = root / ".local" / "jobs" / "staged"
            receipts = root / ".local" / "jobs" / "receipts"
            staged.mkdir(parents=True)
            receipts.mkdir(parents=True)
            (staged / "job-1.json").write_text("{}", encoding="utf-8")
            (staged / "job-1.stage.json").write_text("{}", encoding="utf-8")
            (receipts / "job-1.json").write_text("{}", encoding="utf-8")
            (root / ".local" / "preflight.latest.json").write_text(
                json.dumps({"status": "pass"}), encoding="utf-8"
            )
            (root / ".local" / "acceptance.latest.json").write_text(
                json.dumps({"status": "partial", "tier": "P1"}),
                encoding="utf-8",
            )
            payload = build_status(repo_root=root)
            validate_payload(payload, "local/local_status.schema.json")
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(payload["repo_request_count"], 1)
            self.assertEqual(payload["staged_job_count"], 1)
            self.assertEqual(payload["receipt_count"], 1)
            self.assertEqual(payload["preflight_status"], "pass")
            self.assertEqual(payload["acceptance_status"], "partial")
            self.assertEqual(payload["acceptance_tier"], "P1")
            self.assertEqual(payload["active_job_count"], 0)
            self.assertEqual(payload["stale_job_count"], 0)
            self.assertNotIn(str(root), json.dumps(payload))

    def test_status_distinguishes_active_and_stale_heartbeats(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            for job_id, stamp in (
                ("job-active", "2026-10-05T20:00:20Z"),
                ("job-stale", "2026-10-05T19:59:00Z"),
            ):
                run_dir = root / ".local" / "runs" / job_id
                run_dir.mkdir(parents=True)
                (run_dir / "heartbeat.json").write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "job_id": job_id,
                            "operation": "recording.transcribe",
                            "status": "running",
                            "started_at": "2026-10-05T19:58:00Z",
                            "last_heartbeat_at": stamp,
                            "finished_at": None,
                            "runner_pid": 1234,
                            "privacy": {
                                "absolute_paths_persisted": False,
                                "raw_media_uploaded": False,
                            },
                        }
                    ),
                    encoding="utf-8",
                )
            payload = build_status(
                repo_root=root,
                now=datetime(2026, 10, 5, 20, 0, 30, tzinfo=timezone.utc),
                stale_seconds=30,
            )
            self.assertEqual(payload["active_job_count"], 1)
            self.assertEqual(payload["stale_job_count"], 1)
            self.assertEqual(payload["active_jobs"][0]["job_id"], "job-active")
            self.assertEqual(payload["stale_jobs"][0]["job_id"], "job-stale")

    def test_status_without_acceptance_is_not_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            payload = build_status(repo_root=root)
            self.assertEqual(payload["acceptance_status"], "not_run")
            self.assertIsNone(payload["acceptance_tier"])


if __name__ == "__main__":
    unittest.main()
