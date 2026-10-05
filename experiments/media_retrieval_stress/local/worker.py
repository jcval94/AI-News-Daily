"""Local Media Forensics Worker.

The worker is intentionally conservative:
- no arbitrary commands are accepted from job JSON;
- reference-only sources are never downloaded automatically;
- browser cookies are never exported or persisted by this module;
- large binaries remain outside the git repository.

This first version implements deterministic environment, metadata, hashing and
policy gates. Optional browser/vision stages are represented explicitly in the
result so missing local capabilities are visible rather than silently ignored.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


HERE = Path(__file__).resolve().parent
LAB_ROOT = HERE.parent
JOB_SCHEMA = HERE / "contracts" / "local_job.schema.json"
RESULT_SCHEMA = HERE / "contracts" / "local_result.schema.json"
WORKER_VERSION = "0.1.0"


def lab_home() -> Path:
    configured = os.environ.get("AI_NEWS_MEDIA_LAB_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return (Path(local) / "AI-News-Daily" / "media-lab").resolve()
    return (Path.home() / ".ai-news-daily" / "media-lab").resolve()


def ensure_home() -> dict[str, Path]:
    root = lab_home()
    paths = {name: root / name for name in ("cache", "jobs", "results", "clips", "logs")}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    paths["root"] = root
    return paths


def tool_version(name: str, args: list[str]) -> str | None:
    executable = shutil.which(name)
    if not executable:
        return None
    try:
        proc = subprocess.run(
            [executable, *args],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        text = (proc.stdout or proc.stderr or "").strip().splitlines()
        return text[0][:300] if text else "available"
    except Exception:
        return "available"


def machine_info() -> dict[str, Any]:
    playwright_version = None
    try:
        import importlib.metadata
        playwright_version = importlib.metadata.version("playwright")
    except Exception:
        pass
    return {
        "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
        "worker_version": WORKER_VERSION,
        "ffmpeg": tool_version("ffmpeg", ["-version"]),
        "yt_dlp": tool_version("yt-dlp", ["--version"]),
        "playwright": playwright_version,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact(path: Path, kind: str, retention: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "path": str(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "retention": retention,
    }


def load_and_validate(path: Path, schema_path: Path) -> dict[str, Any]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    payload = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(payload)
    return payload


def yt_dlp_metadata(url: str) -> tuple[dict[str, Any] | None, str | None]:
    executable = shutil.which("yt-dlp")
    if not executable:
        return None, "yt-dlp unavailable"
    proc = subprocess.run(
        [executable, "--skip-download", "--no-playlist", "--dump-single-json", "--", url],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout or "yt-dlp metadata probe failed")[-2000:]
    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError:
        return None, "yt-dlp returned invalid JSON"


def run_job(job_path: Path) -> dict[str, Any]:
    paths = ensure_home()
    job = load_and_validate(job_path, JOB_SCHEMA)
    source = job["source"]
    policy = job["policy"]
    tasks = set(job["tasks"])

    result: dict[str, Any] = {
        "schema_version": 1,
        "job_id": job["job_id"],
        "case_id": job["case_id"],
        "machine": machine_info(),
        "status": "partial",
        "artifacts": [],
        "evidence": [],
        "scene_candidates": [],
        "final": {
            "identity_verified": False,
            "visual_verified": False,
            "rights_status": source["rights_status"],
            "recommended_action": "manual_review",
            "selected_artifact_path": None,
            "selected_scene": None,
        },
    }

    result["evidence"].append({
        "type": "url",
        "value": source["url"],
        "supports": ["identity"],
    })
    result["evidence"].append({
        "type": "rights",
        "value": f"job rights_status={source['rights_status']}; allow_download={policy['allow_download']}",
        "supports": ["rights"],
    })

    if "metadata_probe" in tasks and source["source_type"] == "video":
        metadata, error = yt_dlp_metadata(source["url"])
        if metadata:
            selected = {
                key: metadata.get(key)
                for key in ("id", "title", "description", "duration", "uploader", "upload_date", "webpage_url")
                if metadata.get(key) is not None
            }
            metadata_path = paths["results"] / f"{job['job_id']}.metadata.json"
            metadata_path.write_text(json.dumps(selected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result["artifacts"].append(artifact(metadata_path, "metadata", "cache"))
            if selected.get("title"):
                result["evidence"].append({
                    "type": "title",
                    "value": str(selected["title"])[:5000],
                    "supports": ["identity"],
                })
        elif error:
            result["evidence"].append({
                "type": "technical",
                "value": error,
                "supports": ["quality"],
            })

    # Hard policy boundary: local execution does not make reference-only material reusable.
    may_download = (
        policy["allow_download"]
        and source["rights_status"] == "usable"
        and "download_if_allowed" in tasks
    )
    if "download_if_allowed" in tasks and not may_download:
        result["evidence"].append({
            "type": "rights",
            "value": "download_if_allowed requested but blocked by local rights/policy gate",
            "supports": ["rights"],
        })

    # Optional capabilities remain explicit until installed/implemented.
    pending = sorted(tasks.intersection({
        "browser_probe", "thumbnail_probe", "scene_sample", "ocr",
        "transcript_probe", "semantic_rerank", "dedupe", "clip_plan",
        "resolve_manifest",
    }))
    if pending:
        result["evidence"].append({
            "type": "technical",
            "value": "pending local stages: " + ", ".join(pending),
            "supports": ["quality"],
        })

    if source["rights_status"] == "usable":
        result["final"]["recommended_action"] = "manual_review"
    elif source["rights_status"] == "reference_only":
        result["final"]["recommended_action"] = "keep_reference"
    elif source["rights_status"] == "blocked":
        result["final"]["recommended_action"] = "reject"
    else:
        result["final"]["recommended_action"] = "manual_review"

    result_path = paths["results"] / f"{job['job_id']}.result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Draft202012Validator(json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))).validate(result)
    return result


def doctor() -> None:
    print(json.dumps({
        "home": str(ensure_home()["root"]),
        "machine": machine_info(),
    }, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor")
    run = sub.add_parser("run-job")
    run.add_argument("job", type=Path)

    args = parser.parse_args()
    if args.command == "doctor":
        doctor()
        return
    if args.command == "run-job":
        print(json.dumps(run_job(args.job), ensure_ascii=False, indent=2))
        return
    raise SystemExit(2)


if __name__ == "__main__":
    main()
