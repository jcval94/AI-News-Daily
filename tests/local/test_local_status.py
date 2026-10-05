import json
import tempfile
import unittest
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
            self.assertEqual(payload["repo_request_count"], 1)
            self.assertEqual(payload["staged_job_count"], 1)
            self.assertEqual(payload["receipt_count"], 1)
            self.assertEqual(payload["preflight_status"], "pass")
            self.assertEqual(payload["acceptance_status"], "partial")
            self.assertEqual(payload["acceptance_tier"], "P1")
            self.assertNotIn(str(root), json.dumps(payload))

    def test_status_without_acceptance_is_not_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            payload = build_status(repo_root=root)
            self.assertEqual(payload["acceptance_status"], "not_run")
            self.assertIsNone(payload["acceptance_tier"])


if __name__ == "__main__":
    unittest.main()
