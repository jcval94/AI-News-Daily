import json
import subprocess
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

    def test_expired_request_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            request_dir = root / "local_handoff" / "requests"
            request_dir.mkdir(parents=True)
            payload = sample_job()
            payload["expires_at"] = "2020-01-01T00:00:00Z"
            request = request_dir / "expired.json"
            request.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "expired"):
                stage_request(request, repo_root=root)

    def test_non_handoff_file_cannot_be_staged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            outside = root / "job.json"
            outside.write_text(json.dumps(sample_job()), encoding="utf-8")
            with self.assertRaises(PermissionError):
                stage_request(outside, repo_root=root)


    def test_git_tracked_but_modified_request_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Test User"], check=True)
            request_dir = root / "local_handoff" / "requests"
            request_dir.mkdir(parents=True)
            request = request_dir / "job.json"
            request.write_text(json.dumps(sample_job()), encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-m", "add request"], check=True, capture_output=True)
            payload = sample_job()
            payload["timeout_seconds"] = 61
            request.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "uncommitted changes"):
                stage_request(request, repo_root=root)

    def test_git_untracked_request_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
            request_dir = root / "local_handoff" / "requests"
            request_dir.mkdir(parents=True)
            request = request_dir / "job.json"
            request.write_text(json.dumps(sample_job()), encoding="utf-8")
            with self.assertRaises(PermissionError):
                stage_request(request, repo_root=root)


    def test_staged_job_id_cannot_escape_private_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with self.assertRaisesRegex(ValueError, "Invalid staged job_id"):
                load_staged_job("../../outside", repo_root=root)


if __name__ == "__main__":
    unittest.main()
