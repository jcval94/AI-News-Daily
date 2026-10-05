from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.local.audit import build_harness_audit
from pipeline.local.config import REPO_ROOT
from pipeline.local.paths import RootMap
from pipeline.local.preflight import build_preflight
from pipeline.local.status import build_status
from pipeline.local.toolchain import build_toolchain
from pipeline.schema_validation import validate_payload


P1_REQUIRED_OPERATIONS = (
    "recording.ingest",
    "recording.transcribe",
    "recording.align",
    "resolve.sync_audio",
    "timeline.validate",
    "resolve.import_timeline",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _redact_tree(value: Any, roots: RootMap) -> Any:
    if isinstance(value, str):
        return roots.redact(value)
    if isinstance(value, list):
        return [_redact_tree(item, roots) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _redact_tree(item, roots)
            for key, item in value.items()
        }
    return value


def _run_local_tests(
    *,
    repo_root: Path,
    roots: RootMap,
) -> dict[str, Any]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests/local",
            "-v",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        shell=False,
        check=False,
    )
    stdout = roots.redact(result.stdout or "")
    stderr = roots.redact(result.stderr or "")
    return {
        "status": "pass" if result.returncode == 0 else "fail",
        "exit_code": int(result.returncode),
        "stdout_tail": stdout[-3000:],
        "stderr_tail": stderr[-3000:],
    }


def _load_receipt(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"invalid_json:{exc.__class__.__name__}"
    if not isinstance(payload, dict):
        return None, "not_object"
    try:
        validate_payload(payload, "local/local_receipt.schema.json")
    except Exception as exc:
        return payload, f"schema_invalid:{exc.__class__.__name__}"
    return payload, None


def build_p1_receipt_scope(
    *,
    repo_root: Path,
    target_date: str,
) -> dict[str, Any]:
    receipts_root = repo_root / ".local" / "jobs" / "receipts"
    by_operation: dict[str, list[dict[str, Any]]] = {
        operation: [] for operation in P1_REQUIRED_OPERATIONS
    }
    invalid_receipts: list[str] = []

    if receipts_root.is_dir():
        for path in sorted(receipts_root.glob("*.json")):
            payload, error = _load_receipt(path)
            if payload is None:
                invalid_receipts.append(path.name)
                continue
            if str(payload.get("target_date", "")) != target_date:
                continue
            operation = str(payload.get("operation", ""))
            if operation not in by_operation:
                continue
            if error:
                invalid_receipts.append(path.name)
                by_operation[operation].append(
                    {
                        "job_id": str(payload.get("job_id", path.stem)),
                        "status": "invalid_receipt",
                        "finished_at": str(payload.get("finished_at", "")),
                        "provenance_valid": False,
                    }
                )
                continue
            by_operation[operation].append(
                {
                    "job_id": str(payload["job_id"]),
                    "status": str(payload["status"]),
                    "finished_at": str(payload["finished_at"]),
                    "provenance_valid": True,
                    "source_git_commit": str(
                        payload["provenance"]["source_git_commit"]
                    ),
                    "request_sha256": str(
                        payload["provenance"]["request_sha256"]
                    ),
                }
            )

    selected: dict[str, Any] = {}
    missing: list[str] = []
    failed: list[str] = []
    for operation in P1_REQUIRED_OPERATIONS:
        candidates = by_operation[operation]
        if not candidates:
            selected[operation] = None
            missing.append(operation)
            continue
        latest = sorted(
            candidates,
            key=lambda item: (
                str(item.get("finished_at", "")),
                str(item.get("job_id", "")),
            ),
        )[-1]
        selected[operation] = latest
        if (
            latest.get("status") != "success"
            or not bool(latest.get("provenance_valid"))
        ):
            failed.append(operation)

    if failed:
        status = "fail"
    elif missing:
        status = "partial"
    else:
        status = "pass"

    return {
        "status": status,
        "target_date": target_date,
        "required_operations": list(P1_REQUIRED_OPERATIONS),
        "operations": selected,
        "missing_operations": missing,
        "failed_operations": failed,
        "invalid_receipts": sorted(set(invalid_receipts)),
    }


def build_acceptance_report(
    config: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    probe_resolve: bool = False,
    otio_smoke: bool = False,
    target_date: str | None = None,
    run_tests: bool = True,
) -> dict[str, Any]:
    roots = RootMap.from_config(config, repo_root=repo_root)

    harness = build_harness_audit(repo_root=repo_root)
    preflight = build_preflight(
        config,
        repo_root=repo_root,
        require_resolve=probe_resolve or otio_smoke,
        deep=True,
        otio_smoke=otio_smoke,
    )
    toolchain = build_toolchain(
        config,
        repo_root=repo_root,
        probe_resolve=probe_resolve or otio_smoke,
    )
    local_status = build_status(repo_root=repo_root)
    tests = (
        _run_local_tests(repo_root=repo_root, roots=roots)
        if run_tests
        else {
            "status": "not_run",
            "exit_code": None,
            "stdout_tail": "",
            "stderr_tail": "",
        }
    )

    repository_status = "pass" if harness["status"] == "pass" else "fail"

    if preflight["status"] == "fail" or tests["status"] == "fail":
        workstation_status = "fail"
    elif preflight["status"] == "warn":
        workstation_status = "warn"
    elif tests["status"] == "not_run":
        workstation_status = "warn"
    else:
        workstation_status = "pass"

    resolve_info = preflight["environment"]["resolve"]
    if not (probe_resolve or otio_smoke):
        resolve_status = "not_run"
    elif not bool(resolve_info.get("connected")):
        resolve_status = "fail"
    elif otio_smoke and not bool(resolve_info.get("native_otio_smoke")):
        resolve_status = "fail"
    else:
        resolve_status = "pass"

    p1_scope = (
        build_p1_receipt_scope(
            repo_root=repo_root,
            target_date=target_date,
        )
        if target_date
        else {
            "status": "not_run",
            "target_date": None,
            "required_operations": list(P1_REQUIRED_OPERATIONS),
            "operations": {},
            "missing_operations": [],
            "failed_operations": [],
            "invalid_receipts": [],
        }
    )

    scopes = {
        "repository_harness": {
            "status": repository_status,
            "evidence": {
                "audit_summary": harness["summary"],
                "failed_checks": harness["failed_checks"],
            },
        },
        "workstation": {
            "status": workstation_status,
            "evidence": {
                "preflight_status": preflight["status"],
                "local_tests_status": tests["status"],
                "toolchain_snapshot": True,
            },
        },
        "resolve_real": {
            "status": resolve_status,
            "evidence": {
                "requested": bool(probe_resolve or otio_smoke),
                "connected": bool(resolve_info.get("connected")),
                "version": resolve_info.get("version"),
                "native_otio_smoke": resolve_info.get("native_otio_smoke"),
            },
        },
        "p1_media": {
            "status": p1_scope["status"],
            "evidence": p1_scope,
        },
    }

    requested_statuses = [
        repository_status,
        workstation_status,
    ]
    if probe_resolve or otio_smoke:
        requested_statuses.append(resolve_status)
    if target_date:
        requested_statuses.append(str(p1_scope["status"]))

    if "fail" in requested_statuses:
        overall = "fail"
    elif "partial" in requested_statuses:
        overall = "partial"
    elif "warn" in requested_statuses:
        overall = "warn"
    else:
        overall = "pass"

    blockers: list[str] = []
    warnings: list[str] = []
    for scope_name, scope in scopes.items():
        if scope["status"] == "fail":
            blockers.append(f"{scope_name}:failed")
        elif scope["status"] == "partial":
            blockers.append(f"{scope_name}:incomplete")
        elif scope["status"] == "warn":
            warnings.append(f"{scope_name}:warning")

    blockers.extend(
        f"preflight:{check.get('name', 'unknown')}:{check.get('message', '')}"
        for check in preflight.get("checks", [])
        if check.get("status") == "block"
    )
    warnings.extend(
        f"preflight:{check.get('name', 'unknown')}:{check.get('message', '')}"
        for check in preflight.get("checks", [])
        if check.get("status") == "warn"
    )
    blockers.extend(
        f"harness_audit:{check_id}"
        for check_id in harness.get("failed_checks", [])
    )
    if tests["status"] == "fail":
        blockers.append("local_tests:failed")
    if target_date:
        blockers.extend(
            f"p1:missing:{operation}"
            for operation in p1_scope.get("missing_operations", [])
        )
        blockers.extend(
            f"p1:failed:{operation}"
            for operation in p1_scope.get("failed_operations", [])
        )
        blockers.extend(
            f"p1:invalid_receipt:{name}"
            for name in p1_scope.get("invalid_receipts", [])
        )

    tier = (
        "P1"
        if target_date
        else ("P0_RESOLVE" if probe_resolve or otio_smoke else "P0")
    )
    local_status["acceptance_status"] = overall
    local_status["acceptance_tier"] = tier

    payload = {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "tier": tier,
        "status": overall,
        "requested": {
            "resolve": bool(probe_resolve or otio_smoke),
            "otio_smoke": bool(otio_smoke),
            "target_date": target_date,
        },
        "scopes": scopes,
        "tests": tests,
        "preflight": preflight,
        "environment": preflight["environment"],
        "toolchain": toolchain,
        "local_status": local_status,
        "evidence_boundaries": harness["acceptance_boundaries"],
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "privacy": {
            "absolute_paths_persisted": False,
            "raw_media_uploaded": False,
        },
    }
    payload = _redact_tree(payload, roots)
    validate_payload(
        payload,
        "local/local_acceptance_report.schema.json",
    )
    return payload


def write_acceptance_report(
    path: Path,
    config: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    probe_resolve: bool = False,
    otio_smoke: bool = False,
    target_date: str | None = None,
    run_tests: bool = True,
) -> tuple[Path, dict[str, Any]]:
    payload = build_acceptance_report(
        config,
        repo_root=repo_root,
        probe_resolve=probe_resolve,
        otio_smoke=otio_smoke,
        target_date=target_date,
        run_tests=run_tests,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path, payload
