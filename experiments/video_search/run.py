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

from experiments.video_search.plan import assess_candidates, make_plan
from experiments.video_search.enrichment import enrich
from experiments.video_search.providers import (
    ProviderBlocked, archive_media, blocked, discover, request_json, safe_error,
)
from experiments.youtube_artifacts.download import probe_media, sanitized_metadata, sha256_file, utc_now


MAX_BYTES = 128 * 1024 * 1024
MAX_DURATION = 1800
ROOT = Path(__file__).resolve().parents[2]


def command(argv: list[str], *, timeout=180, directory: Path | None = None) -> str:
    """Kill the process group on timeout/oversize, including downloader ffmpeg children."""
    started = time.monotonic()
    with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, start_new_session=True) as process:
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
                os.killpg(process.pid, signal.SIGKILL)
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
        else:
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


def write_report(output: Path, manifest: dict):
    successes = [v for v in manifest["items"] if v["status"] == "downloaded"]
    expected_events = [v["mention"] for v in manifest.get("plan", {}).get("events", [])]
    missing = [e for e in expected_events if not any(e in v["events"] for v in successes)]
    count = manifest["config"]["count"]
    passed = len(successes) == count and not missing and not manifest.get("fatal_error")
    manifest["summary"] = {"requested": count, "downloaded": len(successes),
                           "failed_attempts": sum(v["status"] == "failed" for v in manifest["items"]),
                           "missing_events": missing, "gate_passed": passed,
                           "transcripts_available": sum(v.get("companions", {}).get("transcript", {}).get("status") == "available" for v in successes),
                           "most_replayed_available": sum(v.get("companions", {}).get("most_replayed", {}).get("status") == "available" for v in successes),
                           "by_source": {s: sum(v["source"] == s for v in successes)
                                         for s in manifest["config"]["sources"]}}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Escape untrusted Markdown/HTML in titles and descriptions.
    def md(text):
        import html
        return html.escape(str(text)).replace("|", "&#124;").replace("\n", " ").replace("`", "&#96;")
    lines = ["# Description-to-video experiment", "", f"Downloaded: **{len(successes)}/{count}**; gate: **{passed}**.",
             "", f"Mode: {manifest['config']['mode']}. Sources: {', '.join(manifest['config']['sources'])}.",
             "", "Event coverage is a title/description match, not visual verification or proof of a claim.",
             "Public availability does not establish permission to republish; consult each source's license.", ""]
    lines += [f"Transcripts: {manifest['summary']['transcripts_available']}; Most Replayed datasets: {manifest['summary']['most_replayed_available']}.",
              "Generated ASR is labelled separately from source captions. Missing replay data is never estimated.", ""]
    if missing:
        lines += ["Missing events: " + md(", ".join(missing)), ""]
    if manifest.get("fatal_error"):
        lines += ["Error: " + md(manifest["fatal_error"]), ""]
    lines += ["| Source | Title | Status | Event matches |", "|---|---|---|---|"]
    for item in manifest["items"]:
        lines.append(f"| {item['source']} | [{md(item['title'])}]({item['url']}) | {item['status']} | {md(', '.join(item['events']))} |")
    (output / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    attribution = ["# Source attribution", "", "License labels are provider metadata, not a legal determination.", ""]
    for item in successes:
        label = item["metadata"].get("license") or item["license"]
        attribution += [f"- [{md(item['title'])}]({item['url']}) — {md(item['creator'])}; {md(label)}."]
    (output / "ATTRIBUTION.md").write_text("\n".join(attribution) + "\n", encoding="utf-8")
    files = sorted(p for p in output.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    (output / "SHA256SUMS").write_text("".join(f"{sha256_file(p)}  {p.relative_to(output)}\n" for p in files))
    return passed


def execute(args, output: Path) -> bool:
    manifest = {"schema_version": 1, "started_at": utc_now(), "description": args.description,
                "config": {"count": args.count, "sources": args.sources.split(","),
                           "mode": args.mode, "clip_seconds": args.clip_seconds,
                           "transcript": getattr(args, "transcript", "off"),
                           "max_bytes_per_video": MAX_BYTES, "max_full_seconds": MAX_DURATION},
                "github": {k: os.environ.get(k) for k in ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")},
                "items": [], "discovery": [], "blocked_sources": {}}
    started = time.monotonic()
    write_report(output, manifest)
    try:
        plan, planning = make_plan(args.description, args.planner, request_json)
        manifest.update(plan=plan.model_dump(), planning=planning)
        (output / "plan.json").write_text(json.dumps(manifest["plan"], ensure_ascii=False, indent=2) + "\n")
        if len(plan.events) > args.count:
            raise ValueError("Video count must cover every explicit event")
        candidates, manifest["discovery"] = discover(plan, manifest["config"]["sources"])
        (output / "candidates.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + "\n")
        if args.planner == "semantic":
            manifest["relevance_assessment"] = assess_candidates(plan, candidates, request_json)
        (output / "candidates.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + "\n")
        attempted, successes = set(), []
        for _ in range(min(max(args.count * 3, 10), 45)):
            if len(successes) == args.count or time.monotonic() - started > 1200:
                break
            item = next_candidate(candidates, attempted, successes, plan.events, manifest["blocked_sources"])
            if item is None:
                break
            attempted.add(item["key"])
            result = dict(item)
            print(f"Attempt {len(attempted)}: {item['source']} {item['id']}", flush=True)
            try:
                result.update(download(item, output, args.mode, args.clip_seconds,
                                       transcript_mode=getattr(args, "transcript", "off")))
                successes.append(result)
            except Exception as error:
                result.update(status="failed", error=safe_error(error))
                if isinstance(error, ProviderBlocked):
                    manifest["blocked_sources"][item["source"]] = safe_error(error)
            manifest["items"].append(result)
            write_report(output, manifest)
    except Exception as error:
        manifest["fatal_error"] = safe_error(error)
    manifest["finished_at"] = utc_now()
    passed = write_report(output, manifest)
    print(json.dumps(manifest["summary"], ensure_ascii=False), flush=True)
    if manifest.get("fatal_error"):
        print(manifest["fatal_error"], flush=True)
    return passed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--description", default=os.environ.get("VIDEO_DESCRIPTION", ""))
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--sources", choices=["youtube", "archive", "youtube,archive"], default="youtube")
    parser.add_argument("--mode", choices=["full", "clip"], default="full")
    parser.add_argument("--clip-seconds", type=int, default=15)
    parser.add_argument("--planner", choices=["semantic", "literal"], default="semantic")
    parser.add_argument("--transcript", choices=["auto", "source", "off"], default="off")
    parser.add_argument("--output", default="video-search-output/run")
    args = parser.parse_args()
    if not 1 <= args.count <= 25 or not 1 <= args.clip_seconds <= 60 or not 1 <= len(args.description.strip()) <= 4000:
        parser.error("Provide a description (1-4000 characters), count 1-25, and clip-seconds 1-60")
    output = Path(args.output).resolve()
    if not output.is_relative_to(ROOT / "video-search-output") or output == ROOT / "video-search-output":
        parser.error("Output must be a new child of this repo's video-search-output/ directory")
    output.mkdir(parents=True, exist_ok=False)
    return 0 if execute(args, output) else 1


if __name__ == "__main__":
    raise SystemExit(main())
