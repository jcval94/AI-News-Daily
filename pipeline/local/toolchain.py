from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import opentimelineio as otio

from pipeline.local.config import REPO_ROOT, resolve_executable
from pipeline.local.paths import RootMap
from pipeline.local.resolve_api import connect_resolve, probe_connected_resolve
from pipeline.schema_validation import validate_payload


def _version(path: Path | None, args: list[str]) -> str | None:
    if path is None:
        return None
    try:
        result = subprocess.run([str(path), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, shell=False, check=False)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    lines = (result.stdout or result.stderr or "").splitlines()
    return lines[0][:240] if lines else "available"


def build_toolchain(config: dict[str, Any], *, repo_root: Path = REPO_ROOT, probe_resolve: bool = False) -> dict[str, Any]:
    roots = RootMap.from_config(config, repo_root=repo_root)
    executables = config["executables"]
    ffmpeg = resolve_executable(executables.get("ffmpeg"), executable_name="ffmpeg", repo_root=repo_root)
    ffprobe = resolve_executable(executables.get("ffprobe"), executable_name="ffprobe", repo_root=repo_root)
    whisperx = resolve_executable(executables.get("whisperx_executable"), executable_name="whisperx", repo_root=repo_root)
    resolve_version = None
    resolve_present = False
    if probe_resolve:
        try:
            resolve, _ = connect_resolve(config)
            info = probe_connected_resolve(resolve)
            resolve_present = True
            resolve_version = str(info.get("version") or "unknown")
        except Exception:
            resolve_present = False
    payload = {
        "schema_version": 1,
        "python": {"version": platform.python_version(), "executable_redacted": roots.redact(sys.executable)},
        "packages": {"opentimelineio": str(otio.__version__)},
        "tools": {
            "ffmpeg": {"present": ffmpeg is not None, "version": _version(ffmpeg, ["-version"])},
            "ffprobe": {"present": ffprobe is not None, "version": _version(ffprobe, ["-version"])},
            "whisperx": {"present": whisperx is not None, "version": _version(whisperx, ["--help"]) if whisperx else None},
            "resolve": {"present": resolve_present, "version": resolve_version},
        },
        "privacy": {"absolute_paths_persisted": False},
    }
    validate_payload(payload, "local/local_toolchain.schema.json")
    return payload
