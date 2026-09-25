from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.local.config import REPO_ROOT
from pipeline.local.jobs import read_job, utc_now
from pipeline.schema_validation import validate_payload


REQUEST_ROOT = REPO_ROOT / "local_handoff" / "requests"
STAGED_ROOT = REPO_ROOT / ".local" / "jobs" / "staged"


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _assert_not_expired(job: dict[str, Any]) -> None:
    raw = job.get("expires_at")
    if not raw:
        return
    try:
        value = str(raw).replace("Z", "+00:00")
        expires = datetime.fromisoformat(value)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError("Invalid expires_at; use ISO-8601") from exc
    if expires.astimezone(timezone.utc) <= datetime.now(timezone.utc):
        raise RuntimeError(f"Local request expired: {job['job_id']}")


def canonical_job_bytes(job: dict[str, Any]) -> bytes:
    return (json.dumps(job, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def stage_request(request_path: Path, *, repo_root: Path = REPO_ROOT) -> tuple[Path, Path, dict[str, Any]]:
    request_root = repo_root / "local_handoff" / "requests"
    request_path = request_path.resolve()
    if not _inside(request_path, request_root):
        raise PermissionError("Only committed local_handoff/requests jobs can be staged")
    job = read_job(request_path)
    _assert_not_expired(job)
    raw = canonical_job_bytes(job)
    digest = hashlib.sha256(raw).hexdigest()
    staged_root = repo_root / ".local" / "jobs" / "staged"
    staged_root.mkdir(parents=True, exist_ok=True)
    staged_job = staged_root / f"{job['job_id']}.json"
    stage_meta = staged_root / f"{job['job_id']}.stage.json"
    if staged_job.exists() or stage_meta.exists():
        raise RuntimeError(f"Job already staged: {job['job_id']}")
    staged_job.write_bytes(raw)
    source_rel = request_path.relative_to(repo_root.resolve()).as_posix()
    payload = {
        "schema_version": 1,
        "job_id": job["job_id"],
        "source_repo_path": source_rel,
        "request_sha256": digest,
        "staged_job_path": f".local/jobs/staged/{job['job_id']}.json",
        "staged_at": utc_now(),
        "execution_requires_local_consent": True,
    }
    validate_payload(payload, "local/local_stage.schema.json")
    stage_meta.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return staged_job, stage_meta, payload


def load_staged_job(job_id: str, *, repo_root: Path = REPO_ROOT) -> tuple[dict[str, Any], dict[str, Any]]:
    staged_root = repo_root / ".local" / "jobs" / "staged"
    staged_job = staged_root / f"{job_id}.json"
    stage_meta = staged_root / f"{job_id}.stage.json"
    if not staged_job.is_file() or not stage_meta.is_file():
        raise FileNotFoundError(f"Staged job not found: {job_id}")
    job = read_job(staged_job)
    meta = json.loads(stage_meta.read_text(encoding="utf-8"))
    validate_payload(meta, "local/local_stage.schema.json")
    digest = hashlib.sha256(canonical_job_bytes(job)).hexdigest()
    if digest != meta["request_sha256"]:
        raise RuntimeError(f"Staged job hash mismatch: {job_id}")
    if str(job["job_id"]) != str(meta["job_id"]):
        raise RuntimeError(f"Staged job identity mismatch: {job_id}")
    return job, meta
