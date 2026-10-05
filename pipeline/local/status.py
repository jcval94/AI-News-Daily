from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.local.config import REPO_ROOT
from pipeline.local.heartbeat import DEFAULT_STALE_SECONDS
from pipeline.schema_validation import validate_payload


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _parse_utc(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _running_heartbeats(
    local: Path,
    *,
    now: datetime,
    stale_seconds: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    active: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    runs = local / "runs"
    heartbeat_files = (
        sorted(runs.glob("*/heartbeat.json"))
        if runs.is_dir()
        else []
    )
    for path in heartbeat_files:
        payload = _read_json(path)
        if not payload or payload.get("status") != "running":
            continue
        stamp = _parse_utc(str(payload.get("last_heartbeat_at", "")))
        if stamp is None:
            age = float(stale_seconds) + 1.0
        else:
            age = max(0.0, (now - stamp).total_seconds())
        item = {
            "job_id": str(payload.get("job_id", "") or path.parent.name),
            "operation": str(payload.get("operation", "") or "unknown"),
            "last_heartbeat_at": str(payload.get("last_heartbeat_at", "") or ""),
            "age_seconds": round(age, 3),
        }
        if age > stale_seconds:
            stale.append(item)
        else:
            active.append(item)
    return active, stale


def build_status(
    *,
    repo_root: Path = REPO_ROOT,
    now: datetime | None = None,
    stale_seconds: float = DEFAULT_STALE_SECONDS,
) -> dict[str, Any]:
    local = repo_root / ".local"
    staged = local / "jobs" / "staged"
    receipts = local / "jobs" / "receipts"
    request_root = repo_root / "local_handoff" / "requests"
    request_files = (
        sorted(p for p in request_root.glob("*.json") if p.is_file())
        if request_root.is_dir()
        else []
    )
    staged_files = (
        sorted(
            p
            for p in staged.glob("*.json")
            if p.is_file() and not p.name.endswith(".stage.json")
        )
        if staged.is_dir()
        else []
    )
    receipt_files = (
        sorted(receipts.glob("*.json"))
        if receipts.is_dir()
        else []
    )
    preflight = _read_json(local / "preflight.latest.json")
    toolchain = _read_json(local / "toolchain.latest.json")
    acceptance = _read_json(local / "acceptance.latest.json")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    active_jobs, stale_jobs = _running_heartbeats(
        local,
        now=current,
        stale_seconds=float(stale_seconds),
    )
    payload = {
        "schema_version": 2,
        "preflight_status": preflight.get("status") if preflight else "not_run",
        "toolchain_snapshot": bool(toolchain),
        "acceptance_status": str(acceptance.get("status")) if acceptance else "not_run",
        "acceptance_tier": (
            str(acceptance.get("tier"))
            if acceptance and acceptance.get("tier")
            else None
        ),
        "repo_request_count": len(request_files),
        "staged_job_count": len(staged_files),
        "receipt_count": len(receipt_files),
        "repo_requests": [
            p.relative_to(repo_root).as_posix()
            for p in request_files
        ],
        "staged_jobs": [p.stem for p in staged_files],
        "latest_receipt": receipt_files[-1].name if receipt_files else None,
        "active_job_count": len(active_jobs),
        "stale_job_count": len(stale_jobs),
        "active_jobs": active_jobs,
        "stale_jobs": stale_jobs,
    }
    validate_payload(payload, "local/local_status.schema.json")
    return payload
