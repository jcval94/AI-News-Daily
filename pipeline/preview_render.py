from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from pipeline.schema_validation import validate_payload


SCHEMA_VERSION = 1
_PREVIEW_WIDTH = 960
_PREVIEW_HEIGHT = 540
_PREVIEW_FPS = 15
_EPSILON = 0.02


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _source_kind(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
        return "image"
    return "video"


def _safe_repo_path(repo_root: Path, logical: str) -> Path:
    path = (repo_root / logical).resolve()
    try:
        path.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"Preview media path escapes repository root: {logical}") from exc
    return path


def _select_visible_placement(
    active: list[dict[str, Any]],
) -> dict[str, Any]:
    v2 = [item for item in active if item.get("track_id") == "V2"]
    if len(v2) > 1:
        raise ValueError("Pre-recording preview found overlapping V2 placements")
    if v2:
        return v2[0]
    v1 = [item for item in active if item.get("track_id") == "V1"]
    if len(v1) != 1:
        raise ValueError(
            f"Pre-recording preview requires exactly one V1 base placement, found {len(v1)}"
        )
    return v1[0]


def build_preview_plan(
    *,
    resolve_plan: dict[str, Any],
    repo_root: Path,
    width: int = _PREVIEW_WIDTH,
    height: int = _PREVIEW_HEIGHT,
    fps: int = _PREVIEW_FPS,
) -> dict[str, Any]:
    if width < 320 or height < 180 or fps < 1:
        raise ValueError("Invalid preview format")
    episode_date = str(resolve_plan.get("episode_date", "") or "").strip()
    if not episode_date:
        raise ValueError("resolve_bridge_plan.json requires episode_date")

    placements = [
        dict(item)
        for item in resolve_plan.get("placements", [])
        if isinstance(item, dict) and item.get("track_id") in {"V1", "V2"}
    ]
    if not placements:
        raise ValueError("Resolve plan has no V1/V2 placements")

    duration = float((resolve_plan.get("summary", {}) or {}).get("duration_seconds", 0) or 0)
    if duration <= 0:
        raise ValueError("Resolve plan requires positive duration")

    boundaries = {0.0, round(duration, 3)}
    for item in placements:
        start = float(item.get("timeline_start_seconds", 0) or 0)
        item_duration = float(item.get("duration_seconds", 0) or 0)
        end = start + item_duration
        if item_duration <= 0 or start < -_EPSILON or end > duration + 0.1:
            raise ValueError(f"Invalid preview placement timing: {item.get('placement_id')}")
        boundaries.add(round(max(0.0, start), 3))
        boundaries.add(round(min(duration, end), 3))

        logical = str(item.get("logical_repo_path", "") or "")
        if not logical:
            raise ValueError(f"Preview placement missing media path: {item.get('placement_id')}")
        physical = _safe_repo_path(repo_root, logical)
        if not physical.is_file():
            raise FileNotFoundError(f"Preview source missing: {logical}")

    points = sorted(boundaries)
    raw_segments: list[dict[str, Any]] = []
    for left, right in zip(points, points[1:]):
        if right <= left + _EPSILON:
            continue
        midpoint = (left + right) / 2
        active = []
        for item in placements:
            start = float(item.get("timeline_start_seconds", 0) or 0)
            end = start + float(item.get("duration_seconds", 0) or 0)
            if start - _EPSILON <= midpoint < end - _EPSILON / 2:
                active.append(item)
        chosen = _select_visible_placement(active)
        placement_start = float(chosen.get("timeline_start_seconds", 0) or 0)
        raw_segments.append({
            "segment_id": f"preview_{len(raw_segments) + 1:03d}",
            "placement_id": str(chosen.get("placement_id", "") or ""),
            "track_id": str(chosen.get("track_id", "") or ""),
            "take_id": chosen.get("take_id"),
            "cue_id": chosen.get("cue_id"),
            "timeline_start_seconds": round(left, 3),
            "timeline_end_seconds": round(right, 3),
            "duration_seconds": round(right - left, 3),
            "source_offset_seconds": round(max(0.0, left - placement_start), 3),
            "logical_repo_path": str(chosen.get("logical_repo_path", "") or ""),
            "source_kind": _source_kind(str(chosen.get("logical_repo_path", "") or "")),
            "placeholder": bool(chosen.get("placeholder")),
        })

    segments: list[dict[str, Any]] = []
    for item in raw_segments:
        if segments:
            previous = segments[-1]
            expected_offset = float(previous["source_offset_seconds"]) + float(previous["duration_seconds"])
            if (
                previous["placement_id"] == item["placement_id"]
                and abs(float(item["source_offset_seconds"]) - expected_offset) <= 0.05
                and abs(float(previous["timeline_end_seconds"]) - float(item["timeline_start_seconds"])) <= 0.05
            ):
                previous["timeline_end_seconds"] = item["timeline_end_seconds"]
                previous["duration_seconds"] = round(
                    float(previous["duration_seconds"]) + float(item["duration_seconds"]), 3
                )
                continue
        segments.append(dict(item))

    cursor = 0.0
    for item in segments:
        if abs(float(item["timeline_start_seconds"]) - cursor) > 0.05:
            raise ValueError(
                f"Preview plan is not contiguous before {item['segment_id']}: "
                f"{cursor:.3f} -> {float(item['timeline_start_seconds']):.3f}"
            )
        cursor = float(item["timeline_end_seconds"])
    if abs(cursor - duration) > 0.05:
        raise ValueError(f"Preview plan ends at {cursor:.3f}, expected {duration:.3f}")

    presenter_seconds = sum(
        float(item["duration_seconds"]) for item in segments if item["track_id"] == "V1"
    )
    broll_seconds = sum(
        float(item["duration_seconds"]) for item in segments if item["track_id"] == "V2"
    )
    placeholder_broll_seconds = sum(
        float(item["duration_seconds"])
        for item in segments
        if item["track_id"] == "V2" and item["placeholder"]
    )
    resolved_broll_seconds = max(0.0, broll_seconds - placeholder_broll_seconds)

    return {
        "schema_version": SCHEMA_VERSION,
        "episode_date": episode_date,
        "status": "pre_recording_preview_plan",
        "source": {
            "resolve_bridge_plan": f"scripts/{episode_date}/resolve_bridge_plan.json",
            "timing_authority": "estimated_pre_recording_timeline",
        },
        "format": {
            "width": int(width),
            "height": int(height),
            "frame_rate_fps": int(fps),
            "video_codec": "libx264",
            "pixel_format": "yuv420p",
            "audio": "silent_aac_stereo",
        },
        "policy": {
            "layer_priority": ["V2", "V1"],
            "resolved_broll_over_presenter": True,
            "missing_broll_slate_over_presenter": True,
            "watermark_required": True,
            "publishable": False,
            "frame_accurate": False,
            "requires_recording_retime": True,
        },
        "summary": {
            "duration_seconds": round(duration, 3),
            "segment_count": len(segments),
            "presenter_seconds": round(presenter_seconds, 3),
            "broll_seconds": round(broll_seconds, 3),
            "resolved_broll_seconds": round(resolved_broll_seconds, 3),
            "placeholder_broll_seconds": round(placeholder_broll_seconds, 3),
            "broll_coverage_ratio": round(broll_seconds / duration, 4),
        },
        "segments": segments,
    }


def _probe_video(path: Path, ffprobe: str) -> dict[str, Any]:
    command = [
        ffprobe,
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
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr.strip() or "ffprobe_failed"}
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "error": "ffprobe_invalid_json"}
    streams = payload.get("streams", [])
    if not streams:
        return {"ok": False, "error": "no_video_stream"}
    return {"ok": True, "payload": payload}


def _decode_smoke(path: Path, ffmpeg: str) -> tuple[bool, str]:
    command = [
        ffmpeg,
        "-v",
        "error",
        "-t",
        "0.5",
        "-i",
        str(path),
        "-an",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return result.returncode == 0, result.stderr.strip()


def _diagnostic_slate(
    path: Path,
    *,
    width: int,
    height: int,
    title: str,
    logical_path: str,
) -> None:
    image = Image.new("RGB", (width, height), (38, 15, 15))
    draw = ImageDraw.Draw(image)
    margin = max(24, width // 28)
    draw.rectangle((0, 0, width, max(48, height // 10)), fill=(84, 20, 20))
    draw.text((margin, margin // 2), "PREVIEW MEDIA FALLBACK", font=_font(max(18, width // 45)), fill=(255, 235, 235))
    draw.text((margin, height // 3), title, font=_font(max(26, width // 30)), fill=(255, 255, 255))
    draw.multiline_text(
        (margin, height // 2),
        "\n".join([logical_path, "FFmpeg could not decode this source.", "The final edit contract is unchanged."]),
        font=_font(max(17, width // 52)),
        fill=(230, 205, 205),
        spacing=8,
    )
    image.save(path, format="PNG", optimize=True)


def _watermark(path: Path, *, width: int) -> None:
    height = max(48, width // 18)
    image = Image.new("RGBA", (width, height), (0, 0, 0, 175))
    draw = ImageDraw.Draw(image)
    text = "PRE-RECORDING PREVIEW | TIMING ESTIMADO | NO PUBLICAR"
    draw.text(
        (max(16, width // 48), max(10, height // 5)),
        text,
        font=_font(max(16, width // 50)),
        fill=(255, 255, 255, 255),
    )
    image.save(path, format="PNG")


def _ffmpeg_filter(segment_count: int, width: int, height: int, fps: int) -> str:
    filters = []
    for index in range(segment_count):
        filters.append(
            f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps={fps},setsar=1,format=yuv420p,"
            f"setpts=PTS-STARTPTS[v{index}]"
        )
    concat_inputs = "".join(f"[v{index}]" for index in range(segment_count))
    filters.append(f"{concat_inputs}concat=n={segment_count}:v=1:a=0[vcat]")
    filters.append(f"[vcat][{segment_count}:v]overlay=0:0:format=auto[vout]")
    return ";".join(filters)


def render_preview(
    *,
    plan: dict[str, Any],
    repo_root: Path,
    output_path: Path,
    validation_path: Path,
    ffmpeg: str | None = None,
    ffprobe: str | None = None,
) -> dict[str, Any]:
    ffmpeg_bin = ffmpeg or shutil.which("ffmpeg")
    ffprobe_bin = ffprobe or shutil.which("ffprobe")
    if not ffmpeg_bin or not ffprobe_bin:
        raise RuntimeError("ffmpeg and ffprobe are required for the pre-recording preview")

    fmt = plan.get("format", {}) if isinstance(plan.get("format"), dict) else {}
    width = int(fmt.get("width", _PREVIEW_WIDTH))
    height = int(fmt.get("height", _PREVIEW_HEIGHT))
    fps = int(fmt.get("frame_rate_fps", _PREVIEW_FPS))
    total = float((plan.get("summary", {}) or {}).get("duration_seconds", 0) or 0)
    segments = [dict(item) for item in plan.get("segments", []) if isinstance(item, dict)]
    if not segments or total <= 0:
        raise ValueError("Preview plan contains no renderable segments")

    warnings: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="pre-recording-preview-") as tmp:
        temp = Path(tmp)
        runtime_sources: list[Path] = []
        for index, segment in enumerate(segments):
            logical = str(segment.get("logical_repo_path", "") or "")
            source = _safe_repo_path(repo_root, logical)
            kind = str(segment.get("source_kind", "") or _source_kind(logical))
            runtime = source
            if kind == "video":
                probe = _probe_video(source, ffprobe_bin)
                smoke_ok, smoke_error = _decode_smoke(source, ffmpeg_bin) if probe.get("ok") else (False, str(probe.get("error")))
                if not probe.get("ok") or not smoke_ok:
                    runtime = temp / f"fallback_{index:03d}.png"
                    _diagnostic_slate(
                        runtime,
                        width=width,
                        height=height,
                        title=str(segment.get("cue_id") or segment.get("placement_id") or "media"),
                        logical_path=logical,
                    )
                    segment["runtime_source_kind"] = "image"
                    warnings.append({
                        "code": "preview_decode_fallback",
                        "segment_id": segment.get("segment_id"),
                        "placement_id": segment.get("placement_id"),
                        "logical_repo_path": logical,
                        "detail": smoke_error or str(probe.get("error", "")),
                    })
                else:
                    segment["runtime_source_kind"] = "video"
            else:
                segment["runtime_source_kind"] = "image"
            runtime_sources.append(runtime)

        watermark = temp / "watermark.png"
        _watermark(watermark, width=width)

        command = [ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error"]
        for segment, source in zip(segments, runtime_sources):
            duration = float(segment["duration_seconds"])
            offset = float(segment.get("source_offset_seconds", 0) or 0)
            if segment["runtime_source_kind"] == "image":
                command.extend([
                    "-loop", "1",
                    "-framerate", str(fps),
                    "-t", f"{duration:.3f}",
                    "-i", str(source),
                ])
            else:
                command.extend([
                    "-stream_loop", "-1",
                    "-ss", f"{offset:.3f}",
                    "-t", f"{duration:.3f}",
                    "-i", str(source),
                ])

        command.extend([
            "-loop", "1",
            "-framerate", str(fps),
            "-t", f"{total:.3f}",
            "-i", str(watermark),
            "-f", "lavfi",
            "-t", f"{total:.3f}",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-filter_complex", _ffmpeg_filter(len(segments), width, height, fps),
            "-map", "[vout]",
            "-map", f"{len(segments) + 1}:a:0",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "30",
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
            "-c:a", "aac",
            "-b:a", "64k",
            "-movflags", "+faststart",
            "-shortest",
            str(output_path),
        ])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                "Pre-recording preview render failed: " + (result.stderr.strip() or "ffmpeg_failed")
            )

    probe_command = [
        ffprobe_bin,
        "-v", "error",
        "-show_entries",
        "stream=index,codec_type,codec_name,width,height,r_frame_rate:format=duration,size",
        "-of", "json",
        str(output_path),
    ]
    probe_result = subprocess.run(probe_command, capture_output=True, text=True, check=False)
    if probe_result.returncode != 0:
        raise RuntimeError("ffprobe could not validate rendered preview")
    probe_payload = json.loads(probe_result.stdout or "{}")
    streams = probe_payload.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio = next((item for item in streams if item.get("codec_type") == "audio"), {})
    actual_duration = float((probe_payload.get("format", {}) or {}).get("duration", 0) or 0)
    size_bytes = int((probe_payload.get("format", {}) or {}).get("size", 0) or 0)
    duration_tolerance = max(1.0, total * 0.005)
    errors = []
    if int(video.get("width", 0) or 0) != width or int(video.get("height", 0) or 0) != height:
        errors.append("resolution_mismatch")
    if abs(actual_duration - total) > duration_tolerance:
        errors.append("duration_mismatch")
    if not audio:
        errors.append("missing_silent_audio_track")
    if size_bytes <= 0:
        errors.append("empty_output")

    validation = {
        "schema_version": 1,
        "episode_date": plan.get("episode_date"),
        "valid": not errors,
        "publishable": False,
        "frame_accurate": False,
        "expected_duration_seconds": round(total, 3),
        "actual_duration_seconds": round(actual_duration, 3),
        "duration_tolerance_seconds": round(duration_tolerance, 3),
        "width": int(video.get("width", 0) or 0),
        "height": int(video.get("height", 0) or 0),
        "video_codec": str(video.get("codec_name", "") or ""),
        "audio_codec": str(audio.get("codec_name", "") or ""),
        "size_bytes": size_bytes,
        "decode_fallback_count": len(warnings),
        "warnings": warnings,
        "errors": errors,
    }
    validation_path.write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if errors:
        raise RuntimeError("Rendered preview failed validation: " + ", ".join(errors))
    return validation


def write_preview(
    *,
    repo_root: Path,
    episode_dir: Path,
    width: int = _PREVIEW_WIDTH,
    height: int = _PREVIEW_HEIGHT,
    fps: int = _PREVIEW_FPS,
    render: bool = True,
    output_path: Path | None = None,
) -> tuple[Path, Path | None, Path | None]:
    resolve_plan_path = episode_dir / "resolve_bridge_plan.json"
    if not resolve_plan_path.is_file():
        raise FileNotFoundError(f"Missing Resolve Bridge plan: {resolve_plan_path}")
    plan = build_preview_plan(
        resolve_plan=_read_json(resolve_plan_path),
        repo_root=repo_root,
        width=width,
        height=height,
        fps=fps,
    )
    validate_payload(plan, "pre_recording_preview.schema.json")
    plan_path = episode_dir / "pre_recording_preview_plan.json"
    plan_path.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if not render:
        return plan_path, None, None

    preview_path = output_path or (episode_dir / "pre_recording_preview.mp4")
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    validation_path = episode_dir / "pre_recording_preview_validation.json"
    validation = render_preview(
        plan=plan,
        repo_root=repo_root,
        output_path=preview_path,
        validation_path=validation_path,
    )
    validation["artifact_scope"] = (
        "canonical_episode_directory"
        if preview_path.parent.resolve() == episode_dir.resolve()
        else "isolated_run_artifact"
    )
    try:
        validation["preview_path"] = preview_path.resolve().relative_to(
            repo_root.resolve()
        ).as_posix()
    except ValueError:
        validation["preview_path"] = str(preview_path)
    validation_path.write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return plan_path, preview_path, validation_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and render the pre-recording rough-cut preview")
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--scripts-dir", default="scripts")
    parser.add_argument("--width", type=int, default=_PREVIEW_WIDTH)
    parser.add_argument("--height", type=int, default=_PREVIEW_HEIGHT)
    parser.add_argument("--fps", type=int, default=_PREVIEW_FPS)
    parser.add_argument("--output", default="")
    parser.add_argument("--plan-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    episode_dir = repo_root / args.scripts_dir / args.target_date
    plan, preview, validation = write_preview(
        repo_root=repo_root,
        episode_dir=episode_dir,
        width=args.width,
        height=args.height,
        fps=args.fps,
        render=not args.plan_only,
        output_path=Path(args.output) if args.output else None,
    )
    print(json.dumps({
        "pre_recording_preview_plan": str(plan),
        "pre_recording_preview": str(preview) if preview else None,
        "validation": str(validation) if validation else None,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
