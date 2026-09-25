from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import opentimelineio as otio

from pipeline.local.config import REPO_ROOT, resolve_executable
from pipeline.local.paths import RootMap
from pipeline.local.resolve_api import connect_resolve, discover_resolve, probe_connected_resolve
from pipeline.local.resolve_smoke import build_smoke_otio, run_resolve_otio_smoke
from pipeline.schema_validation import validate_payload


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    message: str


def _run(argv: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
        check=False,
    )


def _version_check(name: str, path: Path | None, args: list[str]) -> Check:
    if path is None:
        return Check(name, "block", f"{name} executable not found")
    try:
        result = _run([str(path), *args], timeout=15)
    except Exception as exc:
        return Check(name, "block", f"{name} probe failed: {exc}")
    if result.returncode != 0:
        return Check(name, "block", f"{name} returned exit code {result.returncode}")
    first = (result.stdout or result.stderr or "").splitlines()
    return Check(name, "pass", first[0][:220] if first else "available")


def _otio_check() -> Check:
    try:
        with tempfile.TemporaryDirectory(prefix="ai-news-otio-") as tmp:
            path = build_smoke_otio(Path(tmp) / "smoke.otio")
            readback = otio.adapters.read_from_file(str(path))
            if len(readback.tracks) != 1:
                raise RuntimeError("track count changed")
        return Check("opentimelineio", "pass", f"OpenTimelineIO {otio.__version__}")
    except Exception as exc:
        return Check("opentimelineio", "block", f"OTIO round-trip failed: {exc}")


def _ffmpeg_deep_check(ffmpeg: Path, ffprobe: Path) -> list[Check]:
    with tempfile.TemporaryDirectory(prefix="ai-news-ffmpeg-") as tmp:
        sample = Path(tmp) / "smoke.mkv"
        create = _run([
            str(ffmpeg), "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=15",
            "-t", "1", "-c:v", "ffv1", str(sample),
        ], timeout=30)
        if create.returncode != 0:
            return [Check("ffmpeg.synthetic_encode", "block", create.stderr[-500:])]
        probe = _run([
            str(ffprobe), "-v", "error", "-show_streams", "-of", "json", str(sample),
        ], timeout=15)
        if probe.returncode != 0:
            return [Check("ffprobe.synthetic_probe", "block", probe.stderr[-500:])]
        try:
            payload = json.loads(probe.stdout)
        except json.JSONDecodeError as exc:
            return [Check("ffprobe.json", "block", f"invalid JSON: {exc}")]
        if not payload.get("streams"):
            return [Check("ffprobe.streams", "block", "no streams detected")]
        decode = _run([
            str(ffmpeg), "-hide_banner", "-loglevel", "error",
            "-i", str(sample), "-f", "null", "-"
        ], timeout=30)
        return [Check(
            "ffmpeg.synthetic_roundtrip",
            "pass" if decode.returncode == 0 else "block",
            "synthetic encode/probe/decode passed" if decode.returncode == 0 else decode.stderr[-500:],
        )]


def _disk_check(path: Path, minimum_gb: float) -> Check:
    try:
        path.mkdir(parents=True, exist_ok=True)
        free_gb = shutil.disk_usage(path).free / (1024 ** 3)
    except OSError as exc:
        return Check("disk.work_root", "block", f"disk probe failed: {exc}")
    return Check(
        "disk.work_root",
        "pass" if free_gb >= minimum_gb else "block",
        f"{free_gb:.1f} GiB free; hard minimum={minimum_gb:.1f} GiB",
    )


def _gpu_summary() -> dict[str, Any]:
    nvidia = shutil.which("nvidia-smi")
    if not nvidia:
        return {"nvidia_smi": False, "cuda_hint": None, "gpu_names": []}
    result = _run(
        [nvidia, "--query-gpu=name,memory.total", "--format=csv,noheader"],
        timeout=10,
    )
    names = (
        [line.split(",", 1)[0].strip() for line in result.stdout.splitlines() if line.strip()]
        if result.returncode == 0 else []
    )
    return {"nvidia_smi": True, "cuda_hint": bool(names), "gpu_names": names}


def build_preflight(
    config: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    require_resolve: bool = False,
    deep: bool = False,
    otio_smoke: bool = False,
) -> dict[str, Any]:
    roots = RootMap.from_config(config, repo_root=repo_root)
    checks: list[Check] = []
    is_windows = platform.system() == "Windows"
    require_windows = bool(config.get("preflight", {}).get("require_windows", True))
    checks.append(Check(
        "windows",
        "pass" if is_windows else ("block" if require_windows else "warn"),
        platform.platform(),
    ))
    checks.append(Check(
        "python_core",
        "pass" if sys.version_info >= (3, 12) else "block",
        platform.python_version(),
    ))

    exe_cfg = config["executables"]
    ffmpeg = resolve_executable(exe_cfg.get("ffmpeg"), executable_name="ffmpeg", repo_root=repo_root)
    ffprobe = resolve_executable(exe_cfg.get("ffprobe"), executable_name="ffprobe", repo_root=repo_root)
    checks.extend([
        _version_check("ffmpeg", ffmpeg, ["-version"]),
        _version_check("ffprobe", ffprobe, ["-version"]),
        _otio_check(),
        _disk_check(roots.work, float(config.get("preflight", {}).get("hard_min_free_gb", 20))),
    ])
    if deep and ffmpeg and ffprobe:
        checks.extend(_ffmpeg_deep_check(ffmpeg, ffprobe))

    discovery = discover_resolve(config)
    resolve_result: dict[str, Any] = {
        "sdk_discovered": bool(discovery.api_root and discovery.module_dir),
        "readme_discovered": bool(discovery.readme),
        "connected": False,
        "version": None,
        "native_otio_smoke": None,
    }
    if require_resolve or otio_smoke:
        try:
            resolve, _ = connect_resolve(config)
            resolve_result.update(probe_connected_resolve(resolve))
            checks.append(Check("resolve.connection", "pass", "Resolve scripting reachable"))
            if otio_smoke:
                smoke = run_resolve_otio_smoke(
                    resolve,
                    work_root=roots.work,
                    project_name=str(config.get("resolve", {}).get(
                        "acceptance_project_name", "__AI_NEWS_LOCAL_ACCEPTANCE__"
                    )),
                )
                resolve_result["native_otio_smoke"] = bool(smoke["otio_imported"])
                checks.append(Check("resolve.native_otio", "pass", "native OTIO import passed"))
        except Exception as exc:
            checks.append(Check("resolve.connection", "block", str(exc)))
    elif not resolve_result["sdk_discovered"]:
        checks.append(Check(
            "resolve.discovery",
            "warn",
            "Resolve scripting SDK not discovered yet; use doctor --resolve after opening Resolve.",
        ))

    statuses = [item.status for item in checks]
    overall = "fail" if "block" in statuses else ("warn" if "warn" in statuses else "pass")
    environment = {
        "schema_version": 1,
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "python": {"version": platform.python_version(), "minimum_repo_version": "3.12"},
        "gpu": _gpu_summary(),
        "resolve": resolve_result,
        "privacy": {"absolute_paths_persisted": False},
    }
    validate_payload(environment, "local/local_environment.schema.json")

    whisperx = resolve_executable(
        exe_cfg.get("whisperx_executable"), executable_name="whisperx", repo_root=repo_root
    )
    capabilities = {
        "schema_version": 1,
        "harness_version": 1,
        "generated_from_preflight": overall,
        "tools": {
            "ffmpeg": ffmpeg is not None,
            "ffprobe": ffprobe is not None,
            "opentimelineio": any(x.name == "opentimelineio" and x.status == "pass" for x in checks),
            "resolve": bool(resolve_result.get("connected")),
            "whisperx": whisperx is not None,
        },
        "operations": {
            "media.scan": ffprobe is not None,
            "recording.ingest": True,
            "recording.transcribe": whisperx is not None,
            "recording.align": True,
            "resolve.sync_audio": bool(resolve_result.get("connected")),
            "timeline.build": True,
            "timeline.validate": True,
            "resolve.import_timeline": bool(resolve_result.get("connected")),
            "preview.render": ffmpeg is not None and ffprobe is not None,
        },
        "planned_operations": [
            "proxy.generate",
            "captions.burn_or_track",
            "audio.normalize",
            "aligned_timeline.build",
        ],
    }
    validate_payload(capabilities, "local/local_capabilities.schema.json")
    return {
        "schema_version": 1,
        "status": overall,
        "checks": [asdict(item) for item in checks],
        "environment": environment,
        "capabilities": capabilities,
    }
