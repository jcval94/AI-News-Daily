from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.local.config import REPO_ROOT


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def build_status(*, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    local = repo_root / ".local"
    staged = local / "jobs" / "staged"
    receipts = local / "jobs" / "receipts"
    request_root = repo_root / "local_handoff" / "requests"
    request_files = sorted(p for p in request_root.glob("*.json") if p.is_file()) if request_root.is_dir() else []
    staged_files = sorted(p for p in staged.glob("*.json") if p.is_file() and not p.name.endswith(".stage.json")) if staged.is_dir() else []
    receipt_files = sorted(receipts.glob("*.json")) if receipts.is_dir() else []
    preflight = _read_json(local / "preflight.latest.json")
    toolchain = _read_json(local / "toolchain.latest.json")
    return {
        "schema_version": 1,
        "preflight_status": preflight.get("status") if preflight else "not_run",
        "toolchain_snapshot": bool(toolchain),
        "repo_request_count": len(request_files),
        "staged_job_count": len(staged_files),
        "receipt_count": len(receipt_files),
        "repo_requests": [p.relative_to(repo_root).as_posix() for p in request_files],
        "staged_jobs": [p.stem for p in staged_files],
        "latest_receipt": receipt_files[-1].name if receipt_files else None,
    }
