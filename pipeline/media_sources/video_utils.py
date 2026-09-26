from __future__ import annotations
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
RunCommand = Callable[..., subprocess.CompletedProcess[str]]
SAFE_METADATA_FIELDS = (
    "id",
    "title",
    "channel",
    "channel_id",
    "uploader",
    "uploader_id",
    "duration",
    "upload_date",
    "availability",
    "live_status",
    "license",
    "webpage_url",
    "extractor",
    "ext",
    "format_id",
    "width",
    "height",
    "fps",
    "vcodec",
    "acodec",
)
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def sanitized_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep reproducibility metadata while dropping signed media URLs and format inventories."""
    return {key: payload.get(key) for key in SAFE_METADATA_FIELDS if payload.get(key) is not None}

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def probe_media(path: Path, *, runner: RunCommand = subprocess.run) -> dict[str, Any]:
    result = runner(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,format_name:stream=codec_type,codec_name,width,height",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    payload = json.loads(result.stdout)
    format_info = payload.get("format", {}) if isinstance(payload, dict) else {}
    streams = payload.get("streams", []) if isinstance(payload, dict) else []
    video_stream = next(
        (stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"),
        {},
    )
    audio_stream = next(
        (stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "audio"),
        {},
    )
    return {
        "duration_seconds": round(float(format_info.get("duration", 0) or 0), 3),
        "size_bytes": int(format_info.get("size", path.stat().st_size) or path.stat().st_size),
        "container": str(format_info.get("format_name", "") or ""),
        "width": int(video_stream.get("width", 0) or 0),
        "height": int(video_stream.get("height", 0) or 0),
        "video_codec": str(video_stream.get("codec_name", "") or ""),
        "audio_codec": str(audio_stream.get("codec_name", "") or ""),
    }
