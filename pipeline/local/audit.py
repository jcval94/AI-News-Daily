from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.local.config import REPO_ROOT
from pipeline.schema_validation import validate_payload


_REQUIRED_FILES = [
    "pipeline/local/__main__.py",
    "pipeline/local/acceptance.py",
    "pipeline/local/config.py",
    "pipeline/local/jobs.py",
    "pipeline/local/heartbeat.py",
    "pipeline/local/paths.py",
    "pipeline/local/preflight.py",
    "pipeline/local/resolve_api.py",
    "pipeline/local/resolve_smoke.py",
    "pipeline/local/staging.py",
    "pipeline/local/status.py",
    "pipeline/local/toolchain.py",
    "config/local/local_config.schema.json",
    "config/local/local_acceptance_report.schema.json",
    "config/local/local_environment.schema.json",
    "config/local/local_capabilities.schema.json",
    "config/local/local_job.schema.json",
    "config/local/local_heartbeat.schema.json",
    "config/local/local_receipt.schema.json",
    "config/local/local_run_manifest.schema.json",
    "config/local/local_stage.schema.json",
    "config/local/local_status.schema.json",
    "config/local/local_toolchain.schema.json",
    "scripts/local/bootstrap.ps1",
    "scripts/local/doctor.ps1",
    "scripts/local/run_job.ps1",
    "scripts/local/stage_request.ps1",
    "scripts/local/run_staged.ps1",
    "scripts/local/status.ps1",
    "scripts/local/toolchain.ps1",
    "scripts/local/acceptance.ps1",
    "docs/local/README.md",
    "docs/local/contracts.md",
    "docs/local/acceptance.md",
    "local_handoff/README.md",
]

_REQUIRED_GITIGNORE = [
    "recordings/",
    ".local/",
    "local_cache/",
    "local_exports/",
    ".venv-whisperx/",
]


def _contains(path: Path, needle: str) -> bool:
    try:
        return needle in path.read_text(encoding="utf-8")
    except OSError:
        return False


def build_harness_audit(*, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    for relative in _REQUIRED_FILES:
        path = repo_root / relative
        checks.append(
            {
                "id": f"file:{relative}",
                "status": "pass" if path.is_file() else "fail",
                "detail": "present" if path.is_file() else "missing",
            }
        )

    gitignore = repo_root / ".gitignore"
    ignored = set(
        line.strip()
        for line in gitignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    for entry in _REQUIRED_GITIGNORE:
        checks.append(
            {
                "id": f"gitignore:{entry}",
                "status": "pass" if entry in ignored else "fail",
                "detail": "ignored" if entry in ignored else "not_ignored",
            }
        )

    ci = repo_root / ".github/workflows/ci.yml"
    checks.extend(
        [
            {
                "id": "ci:windows_local_harness",
                "status": "pass"
                if _contains(ci, "windows-local-harness:")
                else "fail",
                "detail": "windows job declared",
            },
            {
                "id": "ci:powershell_parse",
                "status": "pass"
                if _contains(ci, "Parse local PowerShell launchers")
                else "fail",
                "detail": "PowerShell syntax guard",
            },
            {
                "id": "security:acceptance_report",
                "status": "pass"
                if _contains(
                    repo_root / "pipeline/local/__main__.py",
                    '"accept"',
                )
                and _contains(
                    repo_root / "scripts/local/acceptance.ps1",
                    "pipeline.local",
                )
                else "fail",
                "detail": "single redacted P0/P1 acceptance report available",
            },
            {
                "id": "security:no_direct_execute",
                "status": "pass"
                if _contains(
                    repo_root / "pipeline/local/__main__.py",
                    "Direct execution from a repo JSON is disabled",
                )
                else "fail",
                "detail": "repo JSON cannot execute directly",
            },
            {
                "id": "security:staged_provenance",
                "status": "pass"
                if _contains(
                    repo_root / "pipeline/local/jobs.py",
                    "Execution requires staged provenance",
                )
                else "fail",
                "detail": "side effects require staged provenance",
            },
            {
                "id": "security:shell_false",
                "status": "pass"
                if _contains(
                    repo_root / "pipeline/local/jobs.py",
                    "shell=False",
                )
                else "fail",
                "detail": "subprocess shell disabled",
            },
            {
                "id": "observability:heartbeat",
                "status": "pass"
                if _contains(
                    repo_root / "pipeline/local/jobs.py",
                    "Heartbeat(",
                )
                and _contains(
                    repo_root / "pipeline/local/status.py",
                    "stale_job_count",
                )
                else "fail",
                "detail": "running jobs emit heartbeats and stale state is visible",
            },
            {
                "id": "security:git_committed_clean",
                "status": "pass"
                if all(
                    _contains(repo_root / "pipeline/local/staging.py", needle)
                    for needle in ("ls-files", "status", "rev-parse")
                )
                else "fail",
                "detail": "staging verifies tracked/clean/commit state",
            },
            {
                "id": "packaging:pipeline_local",
                "status": "pass"
                if _contains(repo_root / "pyproject.toml", 'include = ["app", "pipeline", "pipeline.*"]')
                else "fail",
                "detail": "pipeline.local included in package discovery",
            },
        ]
    )

    failed = [item["id"] for item in checks if item["status"] == "fail"]
    payload = {
        "schema_version": 1,
        "status": "pass" if not failed else "fail",
        "summary": {
            "check_count": len(checks),
            "passed": sum(1 for item in checks if item["status"] == "pass"),
            "failed": len(failed),
        },
        "failed_checks": failed,
        "checks": checks,
        "acceptance_boundaries": {
            "ci_proves": [
                "schema/contracts compile and validate",
                "local Python tests pass on Linux/Windows CI",
                "PowerShell launchers parse on windows-latest",
                "no direct repo-JSON execution path",
                "staged provenance guards remain present",
            ],
            "ci_does_not_prove": [
                "Zenbook hardware characteristics",
                "local FFmpeg build/codec behavior",
                "WhisperX performance on the real machine",
                "DaVinci Resolve scripting connectivity",
                "native OTIO import inside installed Resolve",
                "waveform sync against real recordings",
            ],
        },
    }
    validate_payload(payload, "local/local_harness_audit.schema.json")
    return payload


def write_harness_audit(
    path: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[Path, dict[str, Any]]:
    payload = build_harness_audit(repo_root=repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path, payload
