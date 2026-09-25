from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import opentimelineio as otio

from pipeline.local.config import REPO_ROOT, resolve_executable
from pipeline.local.paths import RootMap
from pipeline.schema_validation import validate_payload

IMPLEMENTED_OPERATIONS = (
    "media.scan",
    "recording.ingest",
    "recording.transcribe",
    "recording.align",
    "resolve.sync_audio",
    "timeline.build",
    "timeline.validate",
    "resolve.import_timeline",
    "preview.render",
)

_ALLOWED_PARAMS: dict[str, set[str]] = {
    "media.scan": {"media"},
    "recording.ingest": {"input_dir"},
    "recording.transcribe": {"recordings_root", "output"},
    "recording.align": {"transcript_bundle"},
    "resolve.sync_audio": {"recordings_root", "alignment"},
    "timeline.build": set(),
    "timeline.validate": {"timeline"},
    "resolve.import_timeline": {"reuse_project"},
    "preview.render": set(),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_job(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Local job must be a JSON object")
    validate_payload(payload, "local/local_job.schema.json")
    operation = str(payload["operation"])
    if operation not in IMPLEMENTED_OPERATIONS:
        raise ValueError(f"Operation is not implemented: {operation}")
    unknown = sorted(set(payload.get("params", {})) - _ALLOWED_PARAMS[operation])
    if unknown:
        raise ValueError(f"Unsupported params for {operation}: {', '.join(unknown)}")
    return payload


def _path_param(
    params: dict[str, Any],
    key: str,
    roots: RootMap,
    *,
    required: bool,
    must_exist: bool = False,
    expect_dir: bool | None = None,
) -> Path | None:
    value = params.get(key)
    if value is None:
        if required:
            raise ValueError(f"Missing required path param: {key}")
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a root_id/relative_path object")
    return roots.resolve_ref(value, must_exist=must_exist, expect_dir=expect_dir)


def _core_python(config: dict[str, Any], repo_root: Path) -> Path:
    return resolve_executable(
        config["executables"].get("python_core"),
        executable_name="python",
        repo_root=repo_root,
    ) or Path(sys.executable).resolve()


def build_command(
    job: dict[str, Any],
    config: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[list[str] | None, dict[str, Any]]:
    validate_payload(job, "local/local_job.schema.json")
    operation = str(job["operation"])
    params = job.get("params", {})
    if operation not in IMPLEMENTED_OPERATIONS:
        raise ValueError(f"Operation is not implemented: {operation}")
    unknown = sorted(set(params) - _ALLOWED_PARAMS[operation])
    if unknown:
        raise ValueError(f"Unsupported params for {operation}: {', '.join(unknown)}")

    roots = RootMap.from_config(config, repo_root=repo_root)
    python = _core_python(config, repo_root)
    date = str(job["target_date"])
    mode = str(job.get("mode", "plan"))

    if operation == "media.scan":
        media = _path_param(params, "media", roots, required=True, must_exist=True, expect_dir=False)
        ffprobe = resolve_executable(
            config["executables"].get("ffprobe"), executable_name="ffprobe", repo_root=repo_root
        )
        if ffprobe is None:
            raise RuntimeError("ffprobe is unavailable")
        return [
            str(ffprobe), "-v", "error", "-show_format", "-show_streams", "-of", "json", str(media)
        ], {"kind": "ffprobe_json"}

    if operation == "recording.ingest":
        input_dir = _path_param(params, "input_dir", roots, required=True, must_exist=True, expect_dir=True)
        return [
            str(python), "-m", "pipeline.recording_ingest",
            "--target-date", date, "--repo-root", str(repo_root),
            "--input-dir", str(input_dir), "--enforce",
        ], {"kind": "python_module"}

    if operation == "recording.transcribe":
        recordings_root = _path_param(
            params, "recordings_root", roots, required=True, must_exist=True, expect_dir=True
        )
        output = _path_param(params, "output", roots, required=True)
        ingest_manifest = repo_root / "scripts" / date / "recording_ingest_manifest.json"
        whisperx = resolve_executable(
            config["executables"].get("whisperx_executable"),
            executable_name="whisperx",
            repo_root=repo_root,
        )
        if whisperx is None:
            raise RuntimeError("WhisperX executable is unavailable")
        wc = config.get("whisperx", {})
        command = [
            str(python), "-m", "pipeline.whisperx_adapter",
            "--ingest-manifest", str(ingest_manifest),
            "--recordings-root", str(recordings_root),
            "--output", str(output),
            "--whisperx-executable", str(whisperx),
            "--model", str(wc.get("model", "large-v3")),
            "--language", str(wc.get("language", "es")),
            "--compute-type", str(wc.get("compute_type", "default")),
            "--batch-size", str(int(wc.get("batch_size", 8))),
            "--vad-method", str(wc.get("vad_method", "silero")),
        ]
        device = str(wc.get("device", "auto"))
        if device != "auto":
            command += ["--device", device]
        return command, {"kind": "python_module"}

    if operation == "recording.align":
        bundle = _path_param(
            params, "transcript_bundle", roots, required=True, must_exist=True, expect_dir=False
        )
        return [
            str(python), "-m", "pipeline.recording_alignment",
            "--target-date", date, "--repo-root", str(repo_root),
            "--transcript-bundle", str(bundle), "--enforce",
        ], {"kind": "python_module"}

    if operation == "resolve.sync_audio":
        recordings_root = _path_param(
            params, "recordings_root", roots, required=True, must_exist=True, expect_dir=True
        )
        alignment = _path_param(
            params, "alignment", roots, required=False, must_exist=True, expect_dir=False
        ) or (repo_root / "scripts" / date / "recording_alignment.json")
        command = [
            str(python), "-m", "pipeline.resolve_alignment_bridge",
            "--alignment", str(alignment), "--recordings-root", str(recordings_root),
        ]
        if mode == "execute":
            command.append("--execute")
        return command, {"kind": "python_module", "resolve": mode == "execute"}

    if operation == "timeline.build":
        return [
            str(python), "-m", "pipeline.otio_export",
            "--target-date", date, "--scripts-dir", str(repo_root / "scripts"),
        ], {"kind": "python_module"}

    if operation == "timeline.validate":
        timeline = _path_param(
            params, "timeline", roots, required=False, must_exist=True, expect_dir=False
        ) or (repo_root / "scripts" / date / "timeline.otio")
        return None, {"kind": "otio_validate", "path": timeline}

    if operation == "resolve.import_timeline":
        command = [
            str(python), "-m", "pipeline.resolve_bridge",
            "--target-date", date, "--repo-root", str(repo_root),
        ]
        if mode == "execute":
            command.append("--execute")
        if bool(params.get("reuse_project")):
            command.append("--reuse-project")
        return command, {"kind": "python_module", "resolve": mode == "execute"}

    if operation == "preview.render":
        command = [
            str(python), "-m", "pipeline.preview_render",
            "--target-date", date, "--repo-root", str(repo_root),
        ]
        if mode != "execute":
            command.append("--plan-only")
        return command, {"kind": "python_module"}

    raise AssertionError(f"Unhandled operation: {operation}")


def _validate_otio(path: Path) -> str:
    timeline = otio.adapters.read_from_file(str(path))
    if not isinstance(timeline, otio.schema.Timeline):
        raise RuntimeError("OTIO file did not decode to a Timeline")
    return json.dumps(
        {"timeline_name": timeline.name, "track_count": len(timeline.tracks)},
        ensure_ascii=False,
    )


def run_job(
    job: dict[str, Any],
    config: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    execute: bool = False,
) -> dict[str, Any]:
    validate_payload(job, "local/local_job.schema.json")
    roots = RootMap.from_config(config, repo_root=repo_root)
    command, metadata = build_command(job, config, repo_root=repo_root)
    redacted_command = (
        [roots.redact(part) for part in command]
        if command else ["<IN_PROCESS_OTIO_VALIDATION>"]
    )

    if not execute or str(job.get("mode", "plan")) != "execute":
        return {
            "schema_version": 1,
            "job_id": job["job_id"],
            "operation": job["operation"],
            "status": "dry_run",
            "command": redacted_command,
            "metadata": {
                k: roots.redact(str(v)) for k, v in metadata.items() if k != "path"
            },
            "privacy": {"absolute_paths_persisted": False, "raw_media_uploaded": False},
            "execution_guard": {
                "cli_execute_requested": bool(execute),
                "job_mode": str(job.get("mode", "plan")),
                "executed": False,
            },
        }

    local_root = repo_root / ".local"
    receipts_dir = local_root / "jobs" / "receipts"
    locks_dir = local_root / "locks"
    run_dir = local_root / "runs" / str(job["job_id"])
    receipts_dir.mkdir(parents=True, exist_ok=True)
    locks_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)

    receipt_path = receipts_dir / f"{job['job_id']}.json"
    if receipt_path.exists():
        raise RuntimeError(
            f"Receipt already exists for job {job['job_id']}; jobs are idempotent by job_id"
        )
    lock_path = locks_dir / f"{job['job_id']}.lock"
    try:
        handle = lock_path.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise RuntimeError(f"Job is already locked: {job['job_id']}") from exc

    started = utc_now()
    status = "failed"
    exit_code = 1
    stdout = ""
    stderr = ""
    try:
        handle.write(started)
        handle.close()
        if metadata["kind"] == "otio_validate":
            stdout = _validate_otio(Path(metadata["path"]))
            exit_code = 0
        else:
            result = subprocess.run(
                command,
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=int(job.get("timeout_seconds", 1800)),
                shell=False,
                check=False,
            )
            exit_code = int(result.returncode)
            stdout = result.stdout or ""
            stderr = result.stderr or ""
        status = "success" if exit_code == 0 else "failed"
    except subprocess.TimeoutExpired as exc:
        status = "timeout"
        exit_code = 124
        stderr = f"Operation timed out: {exc}"
    except Exception as exc:
        status = "failed"
        exit_code = 1
        stderr = str(exc)
    finally:
        try:
            handle.close()
        except Exception:
            pass
        lock_path.unlink(missing_ok=True)

    redacted_stdout = roots.redact(stdout)
    redacted_stderr = roots.redact(stderr)
    (run_dir / "stdout.log").write_text(redacted_stdout, encoding="utf-8")
    (run_dir / "stderr.log").write_text(redacted_stderr, encoding="utf-8")

    receipt = {
        "schema_version": 1,
        "job_id": job["job_id"],
        "operation": job["operation"],
        "target_date": job["target_date"],
        "status": status,
        "started_at": started,
        "finished_at": utc_now(),
        "exit_code": exit_code,
        "command": redacted_command,
        "logs": {
            "stdout": f".local/runs/{job['job_id']}/stdout.log",
            "stderr": f".local/runs/{job['job_id']}/stderr.log",
        },
        "privacy": {"absolute_paths_persisted": False, "raw_media_uploaded": False},
        "result": {
            "stdout_tail": redacted_stdout[-1500:],
            "stderr_tail": redacted_stderr[-1500:],
        },
    }
    validate_payload(receipt, "local/local_receipt.schema.json")
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return receipt
