import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.local.audit import build_harness_audit
from pipeline.schema_validation import validate_payload


class LocalHarnessAuditTests(unittest.TestCase):
    def test_real_repo_harness_audit_passes(self):
        repo_root = Path(__file__).resolve().parents[2]
        payload = build_harness_audit(repo_root=repo_root)
        validate_payload(payload, "local/local_harness_audit.schema.json")
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["summary"]["failed"], 0)
        self.assertTrue(payload["acceptance_boundaries"]["ci_does_not_prove"])

    def test_missing_guard_fails_closed(self):
        repo_root = Path(__file__).resolve().parents[2]
        original = Path.read_text

        def fake_read_text(path, *args, **kwargs):
            if str(path).replace("\\", "/").endswith("pipeline/local/jobs.py"):
                return "no staged provenance guard here"
            return original(path, *args, **kwargs)

        with patch.object(Path, "read_text", fake_read_text):
            payload = build_harness_audit(repo_root=repo_root)
        self.assertEqual(payload["status"], "fail")
        self.assertIn(
            "security:staged_provenance",
            payload["failed_checks"],
        )


if __name__ == "__main__":
    unittest.main()
