import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.local.acceptance import (
    P1_REQUIRED_OPERATIONS,
    build_acceptance_report,
    build_p1_receipt_scope,
)
from pipeline.schema_validation import validate_payload


def config_for(root: Path) -> dict:
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
            "python_core": "auto",
            "whisperx_executable": "auto",
            "ffmpeg": "auto",
            "ffprobe": "auto",
        },
        "resolve": {
            "auto_discover": True,
            "api_root": None,
            "script_lib": None,
            "launch_if_needed": False,
            "connect_timeout_seconds": 45,
            "require_native_otio": True,
            "project_prefix": "AI News Daily",
            "acceptance_project_name": "__AI_NEWS_LOCAL_ACCEPTANCE__",
            "overwrite_existing": False,
        },
        "whisperx": {
            "enabled": False,
            "language": "es",
            "model": "large-v3",
            "device": "auto",
            "compute_type": "auto",
            "batch_size": 8,
            "vad_method": "silero",
            "allow_model_downloads": True,
        },
        "preflight": {
            "hard_min_free_gb": 0,
            "target_free_multiplier": 1.5,
            "require_windows": False,
        },
        "security": {
            "persist_absolute_paths": False,
            "allow_shell": False,
            "network_policy": "models_only",
            "allowed_roots": [
                "repo",
                "recordings",
                "work",
                "cache",
                "previews",
            ],
        },
    }


def receipt(operation: str, target_date: str) -> dict:
    return {
        "schema_version": 2,
        "job_id": f"accept-{operation.replace('.', '-')}-0001",
        "operation": operation,
        "target_date": target_date,
        "status": "success",
        "started_at": "2026-10-05T12:00:00Z",
        "finished_at": "2026-10-05T12:01:00Z",
        "exit_code": 0,
        "command": ["<ROOT:repo>/python"],
        "provenance": {
            "source_repo_path": (
                "local_handoff/requests/"
                + operation.replace(".", "-")
                + ".json"
            ),
            "source_git_commit": "a" * 40,
            "request_sha256": "b" * 64,
            "staged_at": "2026-10-05T11:59:00Z",
        },
        "logs": {
            "stdout": ".local/runs/test/stdout.log",
            "stderr": ".local/runs/test/stderr.log",
        },
        "privacy": {
            "absolute_paths_persisted": False,
            "raw_media_uploaded": False,
        },
        "result": {
            "stdout_tail": "",
            "stderr_tail": "",
        },
    }


class LocalAcceptanceTests(unittest.TestCase):
    def test_p1_requires_all_provenance_valid_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            receipts = root / ".local" / "jobs" / "receipts"
            receipts.mkdir(parents=True)
            for operation in P1_REQUIRED_OPERATIONS:
                payload = receipt(operation, "2026-10-05")
                (receipts / f"{payload['job_id']}.json").write_text(
                    json.dumps(payload),
                    encoding="utf-8",
                )
            scope = build_p1_receipt_scope(
                repo_root=root,
                target_date="2026-10-05",
            )
            self.assertEqual(scope["status"], "pass")
            self.assertEqual(scope["missing_operations"], [])
            self.assertEqual(scope["failed_operations"], [])

    def test_p1_missing_receipt_is_partial_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            scope = build_p1_receipt_scope(
                repo_root=root,
                target_date="2026-10-05",
            )
            self.assertEqual(scope["status"], "partial")
            self.assertEqual(
                sorted(scope["missing_operations"]),
                sorted(P1_REQUIRED_OPERATIONS),
            )

    @patch("pipeline.local.acceptance.build_status")
    @patch("pipeline.local.acceptance.build_toolchain")
    @patch("pipeline.local.acceptance.build_preflight")
    @patch("pipeline.local.acceptance.build_harness_audit")
    @patch("pipeline.local.acceptance._run_local_tests")
    def test_p0_keeps_resolve_not_run_separate(
        self,
        tests_mock,
        audit_mock,
        preflight_mock,
        toolchain_mock,
        status_mock,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            cfg = config_for(root)
            tests_mock.return_value = {
                "status": "pass",
                "exit_code": 0,
                "stdout_tail": "",
                "stderr_tail": "",
            }
            audit_mock.return_value = {
                "status": "pass",
                "summary": {"check_count": 1, "passed": 1, "failed": 0},
                "failed_checks": [],
                "acceptance_boundaries": {
                    "ci_proves": ["contracts"],
                    "ci_does_not_prove": ["real Resolve"],
                },
            }
            preflight_mock.return_value = {
                "status": "pass",
                "environment": {
                    "schema_version": 1,
                    "os": {"system": "Windows", "release": "11", "machine": "x64"},
                    "python": {
                        "version": "3.12.0",
                        "minimum_repo_version": "3.12",
                    },
                    "gpu": {
                        "nvidia_smi": False,
                        "cuda_hint": None,
                        "gpu_names": [],
                    },
                    "resolve": {
                        "sdk_discovered": False,
                        "readme_discovered": False,
                        "connected": False,
                        "version": None,
                        "native_otio_smoke": None,
                    },
                    "privacy": {"absolute_paths_persisted": False},
                },
            }
            toolchain_mock.return_value = {"privacy": {"absolute_paths_persisted": False}}
            status_mock.return_value = {"preflight_status": "pass"}

            payload = build_acceptance_report(
                cfg,
                repo_root=root,
                probe_resolve=False,
                otio_smoke=False,
                run_tests=True,
            )
            validate_payload(
                payload,
                "local/local_acceptance_report.schema.json",
            )
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(
                payload["scopes"]["resolve_real"]["status"],
                "not_run",
            )
            self.assertEqual(
                payload["scopes"]["p1_media"]["status"],
                "not_run",
            )
            self.assertFalse(
                payload["privacy"]["absolute_paths_persisted"]
            )


if __name__ == "__main__":
    unittest.main()
