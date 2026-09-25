from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from pipeline.schema_validation import validate_payload


SCHEMA_VERSION = 1


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def normalize_whisperx_result(
    payload: dict[str, Any],
    *,
    take_id: str,
    retake_number: int,
    source_relative_path: str,
    timebase: str = "video_source",
) -> dict[str, Any]:
    raw_words = [
        item
        for item in payload.get("word_segments", [])
        if isinstance(item, dict)
    ]
    if not raw_words:
        for segment in payload.get("segments", []):
            if not isinstance(segment, dict):
                continue
            raw_words.extend(
                item
                for item in segment.get("words", [])
                if isinstance(item, dict)
            )

    words: list[dict[str, Any]] = []
    previous_end = 0.0
    for item in raw_words:
        word = str(item.get("word", "") or "").strip()
        if not word or item.get("start") is None or item.get("end") is None:
            continue
        start = float(item["start"])
        end = float(item["end"])
        if start < 0 or end < start:
            raise ValueError("WhisperX produced invalid word timestamps")
        if start + 0.05 < previous_end:
            raise ValueError("WhisperX word timestamps are not monotonic")
        previous_end = max(previous_end, end)
        score = item.get("score", item.get("confidence"))
        words.append(
            {
                "word": word,
                "start": round(start, 3),
                "end": round(end, 3),
                "score": (
                    max(0.0, min(1.0, float(score)))
                    if score is not None
                    else None
                ),
            }
        )
    if not words:
        raise ValueError("WhisperX output has no usable word-level timestamps")

    segments = [
        item
        for item in payload.get("segments", [])
        if isinstance(item, dict)
    ]
    transcript_text = " ".join(
        str(item.get("text", "") or "").strip()
        for item in segments
        if str(item.get("text", "") or "").strip()
    ).strip()
    if not transcript_text:
        transcript_text = " ".join(item["word"] for item in words)

    return {
        "take_id": str(take_id),
        "retake_number": int(retake_number),
        "source_relative_path": str(source_relative_path),
        "timebase": str(timebase),
        "language": str(payload.get("language", "") or "unknown"),
        "text": transcript_text,
        "words": words,
        "provider_metadata": {
            "provider": "whisperx",
            "word_timestamp_source": (
                "word_segments"
                if payload.get("word_segments")
                else "segments.words"
            ),
        },
    }


def whisperx_command(
    *,
    executable: str,
    media_path: Path,
    output_dir: Path,
    model: str,
    language: str,
    device: str,
    compute_type: str,
    batch_size: int,
    vad_method: str,
) -> list[str]:
    command = [
        executable,
        str(media_path),
        "--model",
        model,
        "--language",
        language,
        "--output_dir",
        str(output_dir),
        "--output_format",
        "json",
        "--compute_type",
        compute_type,
        "--batch_size",
        str(batch_size),
        "--vad_method",
        vad_method,
        "--verbose",
        "False",
    ]
    if device:
        command.extend(["--device", device])
    return command


def _transcribe_one(
    *,
    media_path: Path,
    take_id: str,
    retake_number: int,
    source_relative_path: str,
    timebase: str,
    executable: str,
    model: str,
    language: str,
    device: str,
    compute_type: str,
    batch_size: int,
    vad_method: str,
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ai-news-whisperx-") as tmp:
        output_dir = Path(tmp)
        command = whisperx_command(
            executable=executable,
            media_path=media_path,
            output_dir=output_dir,
            model=model,
            language=language,
            device=device,
            compute_type=compute_type,
            batch_size=batch_size,
            vad_method=vad_method,
        )
        result = runner(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if int(getattr(result, "returncode", 1)) != 0:
            raise RuntimeError(
                "WhisperX failed for "
                + source_relative_path
                + ": "
                + str(getattr(result, "stderr", "") or "unknown error")
            )
        output_path = output_dir / f"{media_path.stem}.json"
        if not output_path.is_file():
            candidates = sorted(output_dir.glob("*.json"))
            if len(candidates) == 1:
                output_path = candidates[0]
            else:
                raise RuntimeError(
                    f"WhisperX did not produce one JSON output for {source_relative_path}"
                )
        return normalize_whisperx_result(
            _read_json(output_path),
            take_id=take_id,
            retake_number=retake_number,
            source_relative_path=source_relative_path,
            timebase=timebase,
        )


def build_transcript_bundle(
    *,
    ingest_manifest: dict[str, Any],
    recordings_root: Path,
    executable: str,
    model: str = "large-v3",
    language: str = "es",
    device: str = "",
    compute_type: str = "default",
    batch_size: int = 8,
    vad_method: str = "silero",
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    episode_date = str(ingest_manifest.get("episode_date", "") or "")
    if not episode_date:
        raise ValueError("recording_ingest_manifest.json requires episode_date")
    if not recordings_root.is_dir():
        raise FileNotFoundError(
            f"Recording root does not exist: {recordings_root}"
        )

    items: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for take in ingest_manifest.get("takes", []):
        if not isinstance(take, dict):
            continue
        take_id = str(take.get("take_id", "") or "")
        for candidate in take.get("candidates", []):
            if not isinstance(candidate, dict):
                continue
            if candidate.get("status") != "usable_technical":
                continue
            retake = int(candidate.get("retake_number", 0) or 0)
            key = (take_id, retake)
            if not take_id or retake <= 0 or key in seen:
                continue
            seen.add(key)

            external = (
                candidate.get("selected_external_audio", {})
                if isinstance(candidate.get("selected_external_audio"), dict)
                else {}
            )
            video = (
                candidate.get("selected_video", {})
                if isinstance(candidate.get("selected_video"), dict)
                else {}
            )
            video_has_scratch_audio = bool(
                (video.get("inspection", {}) if isinstance(video.get("inspection"), dict) else {}).get(
                    "has_audio_stream"
                )
            )
            if video_has_scratch_audio:
                source_relative = str(video.get("relative_path") or "")
                timebase = "video_source"
            else:
                source_relative = str(
                    external.get("relative_path")
                    or video.get("relative_path")
                    or ""
                )
                timebase = (
                    "external_audio_source"
                    if external.get("relative_path")
                    else "video_source"
                )
            if not source_relative:
                raise ValueError(
                    f"No transcription source for {take_id} r{retake:02d}"
                )
            media_path = (recordings_root / source_relative).resolve()
            try:
                media_path.relative_to(recordings_root.resolve())
            except ValueError as exc:
                raise ValueError(
                    f"Transcript media escapes recording root: {source_relative}"
                ) from exc
            if not media_path.is_file():
                raise FileNotFoundError(
                    f"Transcript media missing: {source_relative}"
                )
            items.append(
                _transcribe_one(
                    media_path=media_path,
                    take_id=take_id,
                    retake_number=retake,
                    source_relative_path=source_relative,
                    timebase=timebase,
                    executable=executable,
                    model=model,
                    language=language,
                    device=device,
                    compute_type=compute_type,
                    batch_size=batch_size,
                    vad_method=vad_method,
                    runner=runner,
                )
            )

    if not items:
        raise ValueError("No usable recording candidates were available for WhisperX")
    return {
        "schema_version": SCHEMA_VERSION,
        "episode_date": episode_date,
        "provider": "whisperx",
        "provider_config": {
            "model": model,
            "language": language,
            "device": device or "whisperx_default",
            "compute_type": compute_type,
            "batch_size": int(batch_size),
            "vad_method": vad_method,
            "alignment_enabled": True,
        },
        "items": items,
    }



def _srt_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(float(seconds) * 1000)))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def render_srt(item: dict[str, Any], *, max_words_per_caption: int = 10) -> str:
    words = [dict(x) for x in item.get("words", []) if isinstance(x, dict)]
    if not words:
        raise ValueError("Cannot render SRT without word timestamps")
    max_words = max(1, int(max_words_per_caption))
    blocks: list[str] = []
    for index in range(0, len(words), max_words):
        chunk = words[index : index + max_words]
        start = float(chunk[0].get("start", 0) or 0)
        end = float(chunk[-1].get("end", start) or start)
        text = " ".join(str(word.get("word", "") or "").strip() for word in chunk).strip()
        if not text:
            continue
        blocks.extend(
            [
                str(len(blocks) // 4 + 1),
                f"{_srt_timestamp(start)} --> {_srt_timestamp(end)}",
                text,
                "",
            ]
        )
    return "\n".join(blocks).rstrip() + "\n"


def write_resolve_srt_sidecars(
    bundle: dict[str, Any],
    *,
    output_dir: Path,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for item in bundle.get("items", []):
        if not isinstance(item, dict):
            continue
        take_id = str(item.get("take_id", "") or "").strip()
        retake = int(item.get("retake_number", 0) or 0)
        if not take_id or retake <= 0:
            continue
        path = output_dir / f"{take_id}__r{retake:02d}.srt"
        path.write_text(render_srt(item), encoding="utf-8")
        paths.append(path)
    return paths

def write_transcript_bundle(
    *,
    ingest_manifest_path: Path,
    recordings_root: Path,
    output_path: Path,
    executable: str | None = None,
    model: str = "large-v3",
    language: str = "es",
    device: str = "",
    compute_type: str = "default",
    batch_size: int = 8,
    vad_method: str = "silero",
) -> tuple[Path, dict[str, Any]]:
    resolved_executable = executable or shutil.which("whisperx")
    if not resolved_executable:
        raise RuntimeError(
            "WhisperX is not installed on this local machine. "
            "Install the optional local tool first; it is intentionally not a repository dependency."
        )
    bundle = build_transcript_bundle(
        ingest_manifest=_read_json(ingest_manifest_path),
        recordings_root=recordings_root,
        executable=resolved_executable,
        model=model,
        language=language,
        device=device,
        compute_type=compute_type,
        batch_size=batch_size,
        vad_method=vad_method,
    )
    validate_payload(bundle, "recording_transcript_bundle.schema.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    sidecars = write_resolve_srt_sidecars(
        bundle,
        output_dir=output_path.parent / "resolve_srt",
    )
    bundle["resolve_srt_sidecars"] = [
        path.relative_to(output_path.parent).as_posix() for path in sidecars
    ]
    output_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path, bundle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run optional local WhisperX and normalize word timestamps"
    )
    parser.add_argument("--ingest-manifest", required=True)
    parser.add_argument("--recordings-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--whisperx-executable", default="")
    parser.add_argument("--model", default="large-v3")
    parser.add_argument("--language", default="es")
    parser.add_argument("--device", default="")
    parser.add_argument("--compute-type", default="default")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--vad-method", choices=["silero", "pyannote"], default="silero")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path, bundle = write_transcript_bundle(
        ingest_manifest_path=Path(args.ingest_manifest).resolve(),
        recordings_root=Path(args.recordings_root).resolve(),
        output_path=Path(args.output).resolve(),
        executable=args.whisperx_executable or None,
        model=args.model,
        language=args.language,
        device=args.device,
        compute_type=args.compute_type,
        batch_size=args.batch_size,
        vad_method=args.vad_method,
    )
    print(
        json.dumps(
            {
                "transcript_bundle": str(output_path),
                "item_count": len(bundle["items"]),
                "provider": bundle["provider"],
                "resolve_srt_sidecars": len(bundle.get("resolve_srt_sidecars", [])),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
