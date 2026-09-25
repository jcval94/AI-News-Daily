import json
import tempfile
import unittest
from pathlib import Path

from pipeline.local.staging import load_staged_job, stage_request


def sample_job():
    return {
        "schema_version": 1,
        "job_id": "stage-test-0001",
        "operation": "timeline.build",
        "target_date": "2026-09-25",
        "mode": "execute",
        "requested_by": "assistant",
        "created_at": "2026-09-25T12:00:00Z",
        "timeout_seconds": 60,
        "params": {},
    }


class LocalStagingTests(unittest.TestCase):
    def test_only_repo_request_root_can_be_staged_and_hash_is_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            request_dir = root / "local_handoff" / "requests"
            request_dir.mkdir(parents=True)
            request = request_dir / "job.json"
            request.write_text(json.dumps(sample_job()), encoding="utf-8")
            staged, meta, payload = stage_request(request, repo_root=root)
            self.assertTrue(staged.is_file())
            self.assertTrue(meta.is_file())
            self.assertEqual(len(payload["request_sha256"]), 64)
            job, metadata = load_staged_job("stage-test-0001", repo_root=root)
            self.assertEqual(job["operation"], "timeline.build")
            self.assertEqual(metadata["request_sha256"], payload["request_sha256"])

    def test_staged_job_tamper_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            request_dir = root / "local_handoff" / "requests"
            request_dir.mkdir(parents=True)
            request = request_dir / "job.json"
            request.write_text(json.dumps(sample_job()), encoding="utf-8")
            staged, _, _ = stage_request(request, repo_root=root)
            data = json.loads(staged.read_text(encoding="utf-8"))
            data["target_date"] = "2026-09-26"
            staged.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "hash mismatch"):
                load_staged_job("stage-test-0001", repo_root=root)

    def test_non_handoff_file_cannot_be_staged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            outside = root / "job.json"
            outside.write_text(json.dumps(sample_job()), encoding="utf-8")
            with self.assertRaises(PermissionError):
                stage_request(outside, repo_root=root)


if __name__ == "__main__":
    unittest.main()
