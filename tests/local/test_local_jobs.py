import sys
import tempfile
import unittest
from pathlib import Path

from pipeline.local.jobs import build_command, run_job


def config_for(root: Path):
    return {
        "schema_version": 1,
        "paths": {
            "repo_root": "auto",
            "recordings_root": str(root / "recordings"),
            "work_root": str(root / "work"),
            "cache_root": str(root / "cache"),
            "preview_root": str(root / "previews"),
        },
        "executables": {
            "python_core": sys.executable,
            "whisperx_executable": "auto",
            "ffmpeg": "auto",
            "ffprobe": "auto",
        },
        "resolve": {
            "auto_discover": True, "api_root": None, "script_lib": None,
            "launch_if_needed": False, "connect_timeout_seconds": 45,
            "require_native_otio": True, "project_prefix": "AI News Daily",
            "acceptance_project_name": "__AI_NEWS_LOCAL_ACCEPTANCE__",
            "overwrite_existing": False,
        },
        "whisperx": {
            "enabled": False, "language": "es", "model": "large-v3",
            "device": "auto", "compute_type": "auto", "batch_size": 8,
            "vad_method": "silero", "allow_model_downloads": True,
        },
        "preflight": {"hard_min_free_gb": 0, "target_free_multiplier": 1.5, "require_windows": False},
        "security": {
            "persist_absolute_paths": False, "allow_shell": False,
            "network_policy": "models_only",
            "allowed_roots": ["repo", "recordings", "work", "cache", "previews"],
        },
    }


def job(operation, params=None, mode="plan"):
    return {
        "schema_version": 1, "job_id": "job-test-0001",
        "operation": operation, "target_date": "2026-09-25",
        "mode": mode, "requested_by": "human",
        "created_at": "2026-09-25T12:00:00Z",
        "timeout_seconds": 60, "params": params or {},
    }


class LocalJobTests(unittest.TestCase):
    def test_unknown_shell_like_param_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            malicious = job("timeline.build")
            malicious["params"] = {"command": "del /s /q C:\\"}
            with self.assertRaises(ValueError):
                build_command(malicious, config_for(root), repo_root=root)

    def test_resolve_execute_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command, _ = build_command(job("resolve.import_timeline", mode="plan"), config_for(root), repo_root=root)
            self.assertNotIn("--execute", command)
            command, _ = build_command(job("resolve.import_timeline", mode="execute"), config_for(root), repo_root=root)
            self.assertIn("--execute", command)

    def test_dry_run_has_no_receipt_and_redacts_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            result = run_job(job("timeline.build"), config_for(root), repo_root=root, execute=False)
            self.assertEqual(result["status"], "dry_run")
            self.assertFalse((root / ".local/jobs/receipts/job-test-0001.json").exists())
            self.assertNotIn(str(root), " ".join(result["command"]))


if __name__ == "__main__":
    unittest.main()
