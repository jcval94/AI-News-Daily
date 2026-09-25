"""Run with python -m experiments.video_search.run; no production imports or writes."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from pipeline.media_sources.video_search.plan import assess_candidates, make_plan
from pipeline.media_sources.video_search.enrichment import enrich
from pipeline.media_sources.video_search.providers import (
    ProviderBlocked, archive_media, blocked, discover, request_json, safe_error,
)
from pipeline.media_sources.video_utils import probe_media, sanitized_metadata, sha256_file, utc_now


MAX_BYTES = 128 * 1024 * 1024
MAX_DURATION = 1800
ROOT = Path(__file__).resolve().parents[2]


def command(argv: list[str], *, timeout=180, directory: Path | None = None) -> str:
    """Kill the process group on timeout/oversize, including downloader ffmpeg children."""
    started = time.monotonic()
    with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, start_new_session=not os.environ.get("MEDIA_POOL_WORKER")) as process:
        try:
            while True:
                if time.monotonic() - started > timeout:
                    raise RuntimeError("Command exceeded wall time limit")
                if directory and sum(p.stat().st_size for p in directory.rglob("*") if p.is_file()) > MAX_BYTES * 2:
                    raise RuntimeError("Download exceeded temporary disk limit")
                try:
                    stdout, stderr = process.communicate(timeout=1)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if process.returncode:
                if blocked(stderr):
                    raise ProviderBlocked("YouTube requested human verification or rate limited downloads")
                raise RuntimeError(safe_error(stderr or "Command failed"))
            return stdout
        finally:
            if process.poll() is None:
                os.killpg(os.getpgrp() if os.environ.get("MEDIA_POOL_WORKER") else process.pid, signal.SIGKILL)
                process.communicate()


def validate_media(path: Path, mode: str, seconds: int, expected_duration=None) -> dict:
    media = probe_media(path)
    if not media["video_codec"] or min(media["width"], media["height"]) < 2:
        raise RuntimeError("No decodable video stream")
    if media["height"] > 360 or not 0 < path.stat().st_size <= MAX_BYTES:
        raise RuntimeError("Media exceeds resolution/size budget")
    duration = media["duration_seconds"]
    if duration <= 0 or duration > (seconds + 2 if mode == "clip" else MAX_DURATION):
        raise RuntimeError("Media exceeds duration budget")
    if mode == "full" and expected_duration and abs(duration - expected_duration) > 3:
        raise RuntimeError("Full video is truncated")
    command(["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-t", "1", "-f", "null", "-"], timeout=30)
    return media


def download(item: dict, output: Path, mode: str, seconds: int, transcript_mode="off") -> dict:
    destination = output / "videos" / (item["source"] + "_" + item["id"])
    # Work outside the uploaded directory, then atomically publish verified media.
    # Cancellation can never upload an in-progress raw download as a video asset.
    folder = Path(tempfile.mkdtemp(prefix="video-download-", dir=output.parent))
    try:
        expected_duration = None
        raw = {}
        if item["source"] == "youtube":
            base = [sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-playlist",
                    "--js-runtimes", "node", "--retries", "0", "--fragment-retries", "0",
                    "--socket-timeout", "20", "--no-warnings", "--quiet"]
            raw = json.loads(command([*base, "--skip-download", "--dump-single-json", item["url"]], timeout=90))
            if raw.get("id") != item["id"] or raw.get("availability") != "public":
                raise RuntimeError("YouTube source is not the selected public video")
            if raw.get("live_status") != "not_live" or raw.get("has_drm"):
                raise RuntimeError("Live or DRM video is excluded")
            expected_duration = float(raw.get("duration") or 0)
            if mode == "full" and not 0 < expected_duration <= MAX_DURATION:
                raise RuntimeError("Full video exceeds 30-minute limit or has unknown duration")
            metadata = sanitized_metadata(raw)
            # Signed stream URLs stay in a temporary file outside the artifact.
            with tempfile.TemporaryDirectory() as temporary:
                info = Path(temporary) / "source.json"
                info.write_text(json.dumps(raw), encoding="utf-8")
                argv = [*base, "--load-info-json", str(info), "--format",
                        "b[height<=360][ext=mp4]/bv[height<=360][ext=mp4]+ba[ext=m4a]/b[height<=360]",
                        "--merge-output-format", "mp4", "--max-filesize", str(MAX_BYTES),
                        "--output", str(folder / "source.%(ext)s")]
                if mode == "clip":
                    argv += ["--download-sections", f"*0-{seconds}", "--force-keyframes-at-cuts"]
                command(argv, timeout=240, directory=folder)
            media_files = [p for p in folder.iterdir() if p.suffix in {".mp4", ".webm", ".mkv"}]
            if len(media_files) != 1:
                raise RuntimeError("Downloader did not produce exactly one media file")
            media_path = media_files[0]
        elif item["source"] == "archive":
            url, metadata = archive_media(item)
            raw["archive_captions"] = metadata.pop("_captions", [])
            media_path = folder / "source.mp4"
            if mode == "full":
                remote_probe = json.loads(command([
                    "ffprobe", "-v", "error", "-rw_timeout", "20000000",
                    "-show_entries", "format=duration", "-of", "json", url,
                ], timeout=45))
                expected_duration = float(remote_probe.get("format", {}).get("duration") or 0)
                if not 0 < expected_duration <= MAX_DURATION:
                    raise RuntimeError("Archive video exceeds 30-minute limit or has unknown duration")
                metadata["source_duration_seconds"] = expected_duration
            # Archive exposes downloadable derivatives. Re-encode at bounded resolution/bitrate.
            command(["ffmpeg", "-nostdin", "-v", "error", "-rw_timeout", "20000000",
                     "-i", url, "-t", str(seconds if mode == "clip" else MAX_DURATION + 1),
                     "-map", "0:v:0", "-map", "0:a:0?", "-vf", "scale=-2:360",
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
                     "-maxrate", "600k", "-bufsize", "1200k", "-c:a", "aac", "-b:a", "64k",
                     "-movflags", "+faststart", "-y", str(media_path)], timeout=240, directory=folder)
        else:
            from pipeline.media_sources import public_media
            from pipeline.media_sources.image_search.sources import fetch, Blocked
            from pipeline.media_sources.video_search.alternatives import direct_media
            try:
                url, metadata, hosts = direct_media(item)
            except ProviderBlocked as error:
                if item["source"] == "peertube":
                    raise RuntimeError(str(error)) from None
                raise
            stated = metadata.get("source_duration_seconds")
            if mode == "full" and stated and float(stated) > MAX_DURATION:
                raise ValueError("Public video exceeds 30-minute limit")
            local_source = folder / "download.bin"
            try:
                data = (fetch(url, domains=hosts, max_bytes=256 * 1024 * 1024, timeout=40)
                        if hosts else public_media.fetch(url, max_bytes=256 * 1024 * 1024, timeout=30))
                local_source.write_bytes(data)
                del data
            except (public_media.AccessDenied, Blocked) as error:
                # One blocked federated instance must not disable all PeerTube.
                if item["source"] == "peertube":
                    raise RuntimeError(str(error)) from None
                raise ProviderBlocked(str(error)) from None
            # Probe/transcode local bytes only: remote media cannot introduce
            # arbitrary network reads through nested playlist manifests.
            source_probe = probe_media(local_source, runner=lambda argv, **kwargs: subprocess.run(
                [argv[0], "-protocol_whitelist", "file,pipe", *argv[1:]], **kwargs))
            expected_duration = source_probe["duration_seconds"]
            if stated and abs(expected_duration - float(stated)) > 3:
                raise ValueError("Downloaded source duration differs from provider metadata")
            if metadata.get("source_has_audio") is True and not source_probe["audio_codec"]:
                raise ValueError("Downloaded source lacks the declared audio stream")
            if mode == "full" and not 0 < expected_duration <= MAX_DURATION:
                raise ValueError("Public video exceeds 30-minute limit or has unknown duration")
            media_path = folder / "source.mp4"
            command(["ffmpeg", "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe",
                     "-i", str(local_source), "-t", str(seconds if mode == "clip" else MAX_DURATION + 1),
                     "-map", "0:v:0", "-map", "0:a:0?", "-vf", "scale=-2:360",
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-maxrate", "600k",
                     "-bufsize", "1200k", "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart",
                     "-y", str(media_path)], timeout=240)
            local_source.unlink()
        media = validate_media(media_path, mode, seconds, expected_duration)
        companions = enrich(media_path, folder, raw, media, item["source"], mode, transcript_mode, command)
        metadata_path = folder / "metadata.json"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = {"status": "downloaded", "path": str((destination / media_path.name).relative_to(output)),
                "sha256": sha256_file(media_path), "media": media, "metadata": metadata,
                "companions": companions,
                "segment": {"mode": mode, "start_seconds": 0,
                            "end_seconds": media["duration_seconds"]}}
        destination.parent.mkdir(parents=True, exist_ok=True)
        folder.rename(destination)
        return result
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def duration_priority(value):
    if not isinstance(value, (int, float)) or not 0 < value < float("inf"):
        return (1, 0)
    return (0 if value <= 300 else 2, value)


def next_candidate(candidates, attempted, successful, events, blocked_sources):
    remaining = [c for c in candidates if c["relevant"] and c["key"] not in attempted
                 and c["source"] not in blocked_sources]
    # Stable order within each duration tier preserves semantic relevance.
    # Known short videos first, unknown lengths second, known long videos last.
    remaining.sort(key=lambda c: duration_priority(c.get("duration_seconds")))
    covered = {e for item in successful for e in item["events"]}
    for event in events:
        if event.mention not in covered:
            specific = [c for c in remaining if event.mention in c["events"]]
            if specific:
                return specific[0]
    # Preserve ranking, preferring creator diversity after required event coverage.
    creators = [c["creator"] for c in successful]
    diverse = [c for c in remaining if creators.count(c["creator"]) < 3]
    return next(iter(diverse or remaining), None)
