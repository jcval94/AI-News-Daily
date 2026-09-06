from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from experiments.youtube_artifacts import EXPECTED_CATALOG_SIZE, EXPERIMENT_NAME


VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_URL_RE = re.compile(r"^https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})$")
MEDIA_SUFFIXES = {".mkv", ".mov", ".mp4", ".webm"}
ALLOWED_COHORTS = {"famous_open_movie", "random_cc"}
ALLOWED_LICENSE_BASES = {"publisher_license", "youtube_metadata"}
YOUTUBE_EXTRACTOR_ARGS = "player_client=web_embedded;skip=hls,dash"
FORMAT_SELECTOR = (
    "bv*[height<=360][ext=mp4]+ba[ext=m4a]/"
    "bv*[height<=360]+ba/"
    "b[height<=360][ext=mp4]/best[height<=360]"
)
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
RunCommand = Callable[..., subprocess.CompletedProcess[str]]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _safe_error(value: str, *, limit: int = 1200) -> str:
    lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
    message = lines[-1] if lines else "unknown yt-dlp failure"
    message = re.sub(r"https?://\S+", "[remote-url]", message)
    return message[:limit]


def _require_nonempty_string(mapping: dict[str, Any], key: str, *, context: str) -> str:
    value = str(mapping.get(key, "") or "").strip()
    if not value:
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value


def load_catalog(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("catalog must be a JSON object")
    if payload.get("schema_version") != 1:
        raise ValueError("catalog.schema_version must be 1")
    if payload.get("expected_count") != EXPECTED_CATALOG_SIZE:
        raise ValueError(f"catalog.expected_count must be {EXPECTED_CATALOG_SIZE}")

    items = payload.get("items")
    if not isinstance(items, list) or len(items) != EXPECTED_CATALOG_SIZE:
        raise ValueError(f"catalog.items must contain exactly {EXPECTED_CATALOG_SIZE} entries")

    seen_ids: set[str] = set()
    seen_ordinals: set[int] = set()
    for position, item in enumerate(items, start=1):
        context = f"catalog.items[{position - 1}]"
        if not isinstance(item, dict):
            raise ValueError(f"{context} must be an object")
        ordinal = item.get("ordinal")
        if not isinstance(ordinal, int) or isinstance(ordinal, bool):
            raise ValueError(f"{context}.ordinal must be an integer")
        if ordinal in seen_ordinals:
            raise ValueError(f"duplicate ordinal: {ordinal}")
        seen_ordinals.add(ordinal)

        video_id = _require_nonempty_string(item, "video_id", context=context)
        if not VIDEO_ID_RE.fullmatch(video_id):
            raise ValueError(f"invalid YouTube video_id: {video_id}")
        if video_id in seen_ids:
            raise ValueError(f"duplicate YouTube video_id: {video_id}")
        seen_ids.add(video_id)

        source_url = _require_nonempty_string(item, "source_url", context=context)
        match = YOUTUBE_URL_RE.fullmatch(source_url)
        if not match or match.group(1) != video_id:
            raise ValueError(f"{context}.source_url must be the canonical watch URL for {video_id}")
        if item.get("cohort") not in ALLOWED_COHORTS:
            raise ValueError(f"{context}.cohort must be one of {sorted(ALLOWED_COHORTS)}")
        _require_nonempty_string(item, "expected_title", context=context)
        _require_nonempty_string(item, "expected_channel", context=context)
        _require_nonempty_string(item, "selection_reason", context=context)

        evidence = item.get("license_evidence")
        if not isinstance(evidence, dict):
            raise ValueError(f"{context}.license_evidence must be an object")
        if evidence.get("basis") not in ALLOWED_LICENSE_BASES:
            raise ValueError(
                f"{context}.license_evidence.basis must be one of {sorted(ALLOWED_LICENSE_BASES)}"
            )
        license_name = _require_nonempty_string(evidence, "license_name", context=f"{context}.license_evidence")
        if "creative commons" not in _normalize(license_name) and not _normalize(license_name).startswith("cc by"):
            raise ValueError(f"{context} is not explicitly curated under an attribution license")
        for key in ("license_url", "evidence_url", "attribution"):
            value = _require_nonempty_string(evidence, key, context=f"{context}.license_evidence")
            if key.endswith("_url") and not value.startswith("https://"):
                raise ValueError(f"{context}.license_evidence.{key} must use https")

    if seen_ordinals != set(range(1, EXPECTED_CATALOG_SIZE + 1)):
        raise ValueError(f"catalog ordinals must be exactly 1..{EXPECTED_CATALOG_SIZE}")
    payload["items"] = sorted(items, key=lambda item: int(item["ordinal"]))
    return payload


def build_yt_dlp_command(
    item: dict[str, Any],
    *,
    item_dir: Path,
    clip_seconds: int,
    yt_dlp_executable: str,
) -> list[str]:
    output_template = item_dir / f"{item['video_id']}.%(ext)s"
    return [
        yt_dlp_executable,
        "--ignore-config",
        "--no-playlist",
        "--no-write-playlist-metafiles",
        "--js-runtimes",
        "node",
        "--extractor-args",
        f"youtube:{YOUTUBE_EXTRACTOR_ARGS}",
        "--match-filter",
        "!is_live & !was_live",
        "--format",
        FORMAT_SELECTOR,
        "--merge-output-format",
        "mp4",
        "--download-sections",
        f"*0-{clip_seconds}",
        "--force-keyframes-at-cuts",
        "--write-info-json",
        "--clean-info-json",
        "--force-overwrites",
        "--retries",
        "3",
        "--fragment-retries",
        "3",
        "--retry-sleep",
        "http:exp=1:4",
        "--retry-sleep",
        "fragment:exp=1:4",
        "--socket-timeout",
        "30",
        "--concurrent-fragments",
        "4",
        "--newline",
        "--output",
        str(output_template),
        str(item["source_url"]),
    ]


def sanitized_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep reproducibility metadata while dropping signed media URLs and format inventories."""
    return {key: payload.get(key) for key in SAFE_METADATA_FIELDS if payload.get(key) is not None}


def verify_metadata(item: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if str(metadata.get("id", "") or "") != item["video_id"]:
        errors.append("downloaded metadata video ID does not match the catalog")
    if _normalize(metadata.get("channel")) != _normalize(item.get("expected_channel")):
        errors.append(
            f"channel drift: expected {item.get('expected_channel')!r}, got {metadata.get('channel')!r}"
        )
    if str(metadata.get("availability", "") or "") not in {"public", "unlisted"}:
        errors.append(f"unexpected availability: {metadata.get('availability')!r}")
    if str(metadata.get("live_status", "") or "") not in {"", "not_live"}:
        errors.append(f"live content is excluded: {metadata.get('live_status')!r}")

    evidence = item["license_evidence"]
    if evidence["basis"] == "youtube_metadata":
        actual_license = _normalize(metadata.get("license"))
        if "creative commons attribution" not in actual_license:
            errors.append(
                "YouTube metadata no longer declares the expected Creative Commons Attribution license"
            )
    return errors


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


def _find_single(path: Path, pattern: str) -> Path:
    candidates = sorted(path.glob(pattern))
    if len(candidates) != 1:
        raise RuntimeError(f"expected exactly one {pattern} file, found {len(candidates)}")
    return candidates[0]


def download_one(
    item: dict[str, Any],
    *,
    videos_dir: Path,
    clip_seconds: int,
    max_bytes_per_clip: int,
    timeout_seconds: int,
    yt_dlp_executable: str,
    runner: RunCommand = subprocess.run,
) -> dict[str, Any]:
    started_at = utc_now()
    item_dir = videos_dir / f"{int(item['ordinal']):02d}_{item['video_id']}"
    item_dir.mkdir(parents=True, exist_ok=False)
    command = build_yt_dlp_command(
        item,
        item_dir=item_dir,
        clip_seconds=clip_seconds,
        yt_dlp_executable=yt_dlp_executable,
    )
    base_result: dict[str, Any] = {
        "ordinal": item["ordinal"],
        "cohort": item["cohort"],
        "video_id": item["video_id"],
        "source_url": item["source_url"],
        "expected_title": item["expected_title"],
        "expected_channel": item["expected_channel"],
        "selection_reason": item["selection_reason"],
        "license_evidence": item["license_evidence"],
        "started_at_utc": started_at,
    }

    try:
        completed = runner(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if completed.returncode != 0:
            raise RuntimeError(_safe_error(completed.stderr or completed.stdout))

        raw_info_path = _find_single(item_dir, "*.info.json")
        raw_metadata = json.loads(raw_info_path.read_text(encoding="utf-8"))
        if not isinstance(raw_metadata, dict):
            raise RuntimeError("yt-dlp info JSON is not an object")
        metadata = sanitized_metadata(raw_metadata)
        raw_info_path.unlink()

        verification_errors = verify_metadata(item, metadata)
        if verification_errors:
            raise RuntimeError("; ".join(verification_errors))

        media_candidates = sorted(
            path for path in item_dir.iterdir() if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES
        )
        if len(media_candidates) != 1:
            raise RuntimeError(f"expected exactly one media file, found {len(media_candidates)}")
        media_path = media_candidates[0]
        probe = probe_media(media_path, runner=runner)
        if probe["duration_seconds"] <= 0:
            raise RuntimeError("ffprobe reported a non-positive duration")
        if probe["duration_seconds"] > clip_seconds + 3:
            raise RuntimeError(
                f"clip duration {probe['duration_seconds']}s exceeds the {clip_seconds}s budget"
            )
        if probe["height"] <= 0 or probe["height"] > 360:
            raise RuntimeError(f"unexpected output height: {probe['height']}")
        if probe["size_bytes"] <= 0 or probe["size_bytes"] > max_bytes_per_clip:
            raise RuntimeError(
                f"clip size {probe['size_bytes']} exceeds per-clip budget {max_bytes_per_clip}"
            )

        metadata_path = item_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        relative_media = media_path.relative_to(videos_dir.parent).as_posix()
        relative_metadata = metadata_path.relative_to(videos_dir.parent).as_posix()
        return {
            **base_result,
            "status": "success",
            "finished_at_utc": utc_now(),
            "actual_title": metadata.get("title", ""),
            "actual_channel": metadata.get("channel", ""),
            "youtube_declared_license": metadata.get("license"),
            "source_duration_seconds": metadata.get("duration"),
            "clip": {
                "path": relative_media,
                "sha256": sha256_file(media_path),
                **probe,
            },
            "metadata": {
                "path": relative_metadata,
                "sha256": sha256_file(metadata_path),
            },
        }
    except subprocess.TimeoutExpired:
        error = f"download exceeded timeout of {timeout_seconds}s"
    except Exception as exc:  # Preserve every per-video result in the artifact report.
        error = _safe_error(str(exc))

    shutil.rmtree(item_dir, ignore_errors=True)
    return {
        **base_result,
        "status": "failed",
        "finished_at_utc": utc_now(),
        "error": error,
    }


def _tool_version(command: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            list(command),
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception as exc:
        return f"unavailable ({type(exc).__name__})"
    first_line = (result.stdout or result.stderr).splitlines()
    return first_line[0].strip() if first_line else "unknown"


def build_manifest(
    *,
    catalog_path: Path,
    clip_seconds: int,
    workers: int,
    max_bytes_per_clip: int,
    required_successes: int,
    results: list[dict[str, Any]],
    yt_dlp_executable: str,
) -> dict[str, Any]:
    ordered = sorted(results, key=lambda item: int(item["ordinal"]))
    success_count = sum(item["status"] == "success" for item in ordered)
    total_bytes = sum(
        int((item.get("clip") or {}).get("size_bytes", 0) or 0)
        for item in ordered
        if item["status"] == "success"
    )
    return {
        "schema_version": 1,
        "experiment": EXPERIMENT_NAME,
        "generated_at_utc": utc_now(),
        "github": {
            "repository": os.getenv("GITHUB_REPOSITORY", ""),
            "run_id": os.getenv("GITHUB_RUN_ID", ""),
            "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", ""),
            "sha": os.getenv("GITHUB_SHA", ""),
            "ref": os.getenv("GITHUB_REF", ""),
        },
        "policy": {
            "isolated_from_production": True,
            "production_imports_this_package": False,
            "artifact_only": True,
            "canonical_media_promotion": False,
            "license_catalog_required": True,
            "manual_review_still_required_before_editorial_reuse": True,
        },
        "configuration": {
            "catalog": catalog_path.as_posix(),
            "format_selector": FORMAT_SELECTOR,
            "youtube_extractor_args": YOUTUBE_EXTRACTOR_ARGS,
            "requested_videos": len(ordered),
            "clip_seconds": clip_seconds,
            "maximum_height": 360,
            "workers": workers,
            "max_bytes_per_clip": max_bytes_per_clip,
            "required_successes": required_successes,
        },
        "tool_versions": {
            "python": sys.version.split()[0],
            "yt_dlp": _tool_version([yt_dlp_executable, "--version"]),
            "ffmpeg": _tool_version(["ffmpeg", "-version"]),
            "node": _tool_version(["node", "--version"]),
        },
        "summary": {
            "requested": len(ordered),
            "succeeded": success_count,
            "failed": len(ordered) - success_count,
            "required_successes": required_successes,
            "gate_passed": success_count >= required_successes,
            "total_clip_bytes": total_bytes,
        },
        "items": ordered,
    }


def write_supporting_files(output_dir: Path, manifest: dict[str, Any]) -> None:
    successful = [item for item in manifest["items"] if item["status"] == "success"]
    checksums: list[tuple[str, str]] = []
    for item in successful:
        checksums.append((item["clip"]["path"], item["clip"]["sha256"]))
        checksums.append((item["metadata"]["path"], item["metadata"]["sha256"]))
    (output_dir / "SHA256SUMS").write_text(
        "".join(f"{digest}  {path}\n" for path, digest in sorted(checksums)),
        encoding="utf-8",
    )

    attribution_lines = [
        "# Attribution",
        "",
        "Every retained clip is an excerpt (start at 00:00), capped at 360p and remuxed/re-encoded as needed.",
        "",
    ]
    for item in successful:
        evidence = item["license_evidence"]
        attribution_lines.extend(
            [
                f"## {int(item['ordinal']):02d}. {item['actual_title']}",
                "",
                f"- Credit: {evidence['attribution']}",
                f"- Channel: {item['actual_channel']}",
                f"- Source: {item['source_url']}",
                f"- License: [{evidence['license_name']}]({evidence['license_url']})",
                f"- Evidence: {evidence['evidence_url']}",
                f"- Modification: excerpted to {item['clip']['duration_seconds']} seconds at no more than 360p.",
                "",
            ]
        )
    (output_dir / "ATTRIBUTION.md").write_text("\n".join(attribution_lines), encoding="utf-8")

    summary = manifest["summary"]
    summary_lines = [
        "# YouTube artifact experiment",
        "",
        f"Result: **{summary['succeeded']}/{summary['requested']}** clips retained; "
        f"gate **{'PASSED' if summary['gate_passed'] else 'FAILED'}**.",
        "",
        "| # | Cohort | Video | Status | Bytes | Detail |",
        "|---:|---|---|---|---:|---|",
    ]
    for item in manifest["items"]:
        if item["status"] == "success":
            title = str(item.get("actual_title", "")).replace("|", "\\|")
            size = item["clip"]["size_bytes"]
            detail = f"{item['clip']['duration_seconds']}s, {item['clip']['height']}p"
        else:
            title = str(item.get("expected_title", "")).replace("|", "\\|")
            size = 0
            detail = str(item.get("error", "failed")).replace("|", "\\|")
        summary_lines.append(
            f"| {item['ordinal']} | {item['cohort']} | {title} | {item['status']} | {size} | {detail} |"
        )
    summary_lines.extend(
        [
            "",
            "This is a time-limited technical artifact, not a production media source or a rights opinion.",
            "",
        ]
    )
    (output_dir / "SUMMARY.md").write_text("\n".join(summary_lines), encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    default_catalog = Path(__file__).with_name("catalog.json")
    parser = argparse.ArgumentParser(
        description="Download a curated ten-video YouTube sample into an ephemeral artifact directory."
    )
    parser.add_argument("--catalog", type=Path, default=default_catalog)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clip-seconds", type=int, default=15)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--required-successes", type=int, default=EXPECTED_CATALOG_SIZE)
    parser.add_argument("--max-mib-per-clip", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--yt-dlp", default="yt-dlp")
    return parser.parse_args(argv)


def run_experiment(args: argparse.Namespace) -> dict[str, Any]:
    if not 1 <= args.clip_seconds <= 60:
        raise ValueError("--clip-seconds must be between 1 and 60")
    if not 1 <= args.workers <= 4:
        raise ValueError("--workers must be between 1 and 4")
    if not 1 <= args.required_successes <= EXPECTED_CATALOG_SIZE:
        raise ValueError(f"--required-successes must be between 1 and {EXPECTED_CATALOG_SIZE}")
    if not 1 <= args.max_mib_per_clip <= 100:
        raise ValueError("--max-mib-per-clip must be between 1 and 100")
    if not 30 <= args.timeout_seconds <= 1200:
        raise ValueError("--timeout-seconds must be between 30 and 1200")
    if shutil.which(args.yt_dlp) is None:
        raise RuntimeError(f"yt-dlp executable not found: {args.yt_dlp}")
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("ffmpeg and ffprobe are required")
    if shutil.which("node") is None:
        raise RuntimeError("Node.js is required for current YouTube JavaScript challenges")

    catalog = load_catalog(args.catalog)
    output_dir = args.output.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    catalog_snapshot = output_dir / "catalog.json"
    catalog_snapshot.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    videos_dir = output_dir / "videos"
    videos_dir.mkdir()
    max_bytes_per_clip = args.max_mib_per_clip * 1024 * 1024

    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                download_one,
                item,
                videos_dir=videos_dir,
                clip_seconds=args.clip_seconds,
                max_bytes_per_clip=max_bytes_per_clip,
                timeout_seconds=args.timeout_seconds,
                yt_dlp_executable=args.yt_dlp,
            ): item
            for item in catalog["items"]
        }
        for future in concurrent.futures.as_completed(futures):
            item = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # A worker bug must still become observable output.
                result = {
                    "ordinal": item["ordinal"],
                    "cohort": item["cohort"],
                    "video_id": item["video_id"],
                    "source_url": item["source_url"],
                    "expected_title": item["expected_title"],
                    "expected_channel": item["expected_channel"],
                    "selection_reason": item["selection_reason"],
                    "license_evidence": item["license_evidence"],
                    "status": "failed",
                    "started_at_utc": utc_now(),
                    "finished_at_utc": utc_now(),
                    "error": _safe_error(f"worker failure: {type(exc).__name__}: {exc}"),
                }
            results.append(result)
            print(
                f"[{int(result['ordinal']):02d}/{EXPECTED_CATALOG_SIZE}] "
                f"{result['video_id']} -> {result['status']}"
            )

    manifest = build_manifest(
        catalog_path=args.catalog,
        clip_seconds=args.clip_seconds,
        workers=args.workers,
        max_bytes_per_clip=max_bytes_per_clip,
        required_successes=args.required_successes,
        results=results,
        yt_dlp_executable=args.yt_dlp,
    )
    manifest["configuration"]["catalog_snapshot"] = {
        "path": catalog_snapshot.relative_to(output_dir).as_posix(),
        "sha256": sha256_file(catalog_snapshot),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_supporting_files(output_dir, manifest)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = run_experiment(args)
    summary = manifest["summary"]
    print(
        f"YouTube artifact experiment: {summary['succeeded']}/{summary['requested']} succeeded; "
        f"total_bytes={summary['total_clip_bytes']}; gate_passed={summary['gate_passed']}"
    )
    return 0 if summary["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
