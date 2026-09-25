from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def media_kind(path: Path | str) -> str:
    return "image" if Path(path).suffix.lower() in _IMAGE_SUFFIXES else "video"


def safe_repo_path(repo_root: Path, logical: str) -> Path:
    path = (repo_root / logical).resolve()
    try:
        path.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"Media path escapes repository root: {logical}") from exc
    return path


def inspect_image(path: Path) -> dict[str, Any]:
    try:
        with Image.open(path) as image:
            width, height = image.size
            image.verify()
    except Exception as exc:
        return {
            "ok": False,
            "kind": "image",
            "error_code": "image_decode_failed",
            "error": str(exc),
        }
    return {
        "ok": True,
        "kind": "image",
        "width": int(width),
        "height": int(height),
        "duration_seconds": None,
        "codec": None,
    }


def inspect_video(
    path: Path,
    *,
    ffprobe: str | None = None,
    ffmpeg: str | None = None,
    smoke_seconds: float = 0.5,
) -> dict[str, Any]:
    ffprobe_bin = ffprobe or shutil.which("ffprobe")
    ffmpeg_bin = ffmpeg or shutil.which("ffmpeg")
    if not ffprobe_bin or not ffmpeg_bin:
        return {
            "ok": False,
            "kind": "video",
            "error_code": "ffmpeg_unavailable",
            "error": "ffmpeg and ffprobe are required",
        }

    probe_command = [
        ffprobe_bin,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,width,height,r_frame_rate:format=duration",
        "-of",
        "json",
        str(path),
    ]
    probe = subprocess.run(probe_command, capture_output=True, text=True, check=False)
    if probe.returncode != 0:
        return {
            "ok": False,
            "kind": "video",
            "error_code": "ffprobe_failed",
            "error": probe.stderr.strip() or "ffprobe_failed",
        }
    try:
        payload = json.loads(probe.stdout or "{}")
    except json.JSONDecodeError:
        return {
            "ok": False,
            "kind": "video",
            "error_code": "ffprobe_invalid_json",
            "error": "ffprobe returned invalid JSON",
        }
    streams = payload.get("streams", [])
    if not streams:
        return {
            "ok": False,
            "kind": "video",
            "error_code": "no_video_stream",
            "error": "No video stream found",
        }

    smoke_command = [
        ffmpeg_bin,
        "-v",
        "error",
        "-t",
        f"{max(0.1, float(smoke_seconds)):.3f}",
        "-i",
        str(path),
        "-an",
        "-f",
        "null",
        "-",
    ]
    smoke = subprocess.run(smoke_command, capture_output=True, text=True, check=False)
    if smoke.returncode != 0:
        return {
            "ok": False,
            "kind": "video",
            "error_code": "video_decode_failed",
            "error": smoke.stderr.strip() or "video_decode_failed",
        }

    stream = streams[0]
    try:
        duration = float((payload.get("format", {}) or {}).get("duration", 0) or 0)
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "ok": True,
        "kind": "video",
        "width": int(stream.get("width", 0) or 0),
        "height": int(stream.get("height", 0) or 0),
        "duration_seconds": max(0.0, duration),
        "codec": str(stream.get("codec_name", "") or ""),
        "r_frame_rate": str(stream.get("r_frame_rate", "") or ""),
    }


def inspect_media(
    path: Path,
    *,
    ffprobe: str | None = None,
    ffmpeg: str | None = None,
) -> dict[str, Any]:
    if not path.is_file():
        return {
            "ok": False,
            "kind": media_kind(path),
            "error_code": "missing_file",
            "error": f"Missing file: {path}",
        }
    if media_kind(path) == "image":
        return inspect_image(path)
    return inspect_video(path, ffprobe=ffprobe, ffmpeg=ffmpeg)
