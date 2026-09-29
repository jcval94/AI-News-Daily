from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audio_qa import (
    inspect_ffmpeg_audio,
    inspect_wav,
    validate_edit_wav,
    validate_ffmpeg_audio,
)
from .config import load_tts_config
from .contracts import write_manifest
from .engines import EngineError, render_native
from .sections import load_spoken_sections


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_episode(script: str, scripts_root: Path = Path("scripts")) -> Path:
    if script != "latest":
        candidate = scripts_root / script
        if not candidate.is_dir():
            raise FileNotFoundError(f"Episode not found: {candidate}")
        return candidate
    candidates: list[Path] = []
    for path in scripts_root.iterdir() if scripts_root.exists() else []:
        if not path.is_dir() or not (path / "script_sections.json").is_file():
            continue
        state_path = path / "run_state.json"
        if state_path.is_file():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if state.get("status") != "approved":
                continue
        candidates.append(path)
    if not candidates:
        raise FileNotFoundError("No approved episode with script_sections.json was found")
    return sorted(candidates, key=lambda p: p.name)[-1]


def _repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"TTS source path must live inside the repository: {path}") from exc


def _script_id(episode_dir: Path) -> str:
    digest = hashlib.sha256()
    for name in ("script.txt", "script_sections.json"):
        digest.update((episode_dir / name).read_bytes())
    return digest.hexdigest()


def _ffmpeg() -> str:
    value = shutil.which("ffmpeg")
    if not value:
        raise RuntimeError("ffmpeg is required for 48 kHz edit derivatives and web previews")
    return value


def _convert_edit(native: Path, edit: Path, sample_rate: int) -> None:
    edit.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [_ffmpeg(), "-y", "-v", "error", "-i", str(native), "-ar", str(sample_rate),
         "-ac", "1", "-c:a", "pcm_s16le", str(edit)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        shell=False, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg edit conversion failed: {proc.stderr[-2000:]}")


def _concat_wav(paths: list[Path], output: Path) -> None:
    if not paths:
        raise ValueError("No WAV files to concatenate")
    output.parent.mkdir(parents=True, exist_ok=True)
    params: tuple[int, int, int, str] | None = None
    with wave.open(str(output), "wb") as target:
        for path in paths:
            with wave.open(str(path), "rb") as source:
                current = (
                    source.getnchannels(), source.getsampwidth(),
                    source.getframerate(), source.getcomptype(),
                )
                if params is None:
                    params = current
                    target.setnchannels(current[0])
                    target.setsampwidth(current[1])
                    target.setframerate(current[2])
                    target.setcomptype(current[3], "not compressed")
                elif current != params:
                    raise ValueError(f"WAV concat format mismatch: {path}")
                target.writeframes(source.readframes(source.getnframes()))


def _web_preview(master: Path, output: Path, bitrate: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [_ffmpeg(), "-y", "-v", "error", "-i", str(master),
         "-c:a", "libmp3lame", "-b:a", bitrate, str(output)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        shell=False, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg web preview failed: {proc.stderr[-2000:]}")


def _render_sections_with_engine(
    *,
    sections: list[dict[str, Any]],
    engine: str,
    voice: str,
    config: dict[str, Any],
    run_dir: Path,
    repo_root: Path,
) -> tuple[list[dict[str, Any]], list[Path], float, float, list[str]]:
    tts = config["tts"]
    sample_rate = int(tts["edit_sample_rate_hz"])
    native_dir = run_dir / "audio/native/sections"
    edit_dir = run_dir / "audio/edit/sections"
    text_dir = run_dir / "text/sections"
    logs_dir = run_dir / "logs"
    records: list[dict[str, Any]] = []
    edit_paths: list[Path] = []
    warnings: list[str] = []
    cursor = 0.0
    generation_total = 0.0

    for section in sections:
        stem = section["filename_stem"]
        text_path = text_dir / f"{stem}.txt"
        text_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.write_text(section["spoken_text"] + "\n", encoding="utf-8")
        native_path = native_dir / f"{stem}.wav"
        edit_path = edit_dir / f"{stem}.wav"

        meta = render_native(
            engine=engine,
            voice=voice,
            text_file=text_path,
            output_file=native_path,
            config=config,
            repo_root=repo_root.resolve(),
        )
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / f"{stem}.log").write_text(
            str(meta.get("log_tail") or ""), encoding="utf-8"
        )

        native_metrics = inspect_wav(native_path)
        _convert_edit(native_path, edit_path, sample_rate)
        edit_metrics = inspect_wav(edit_path)
        qa_policy = tts.get("qa", {})
        ffmpeg_metrics = inspect_ffmpeg_audio(
            edit_path,
            silence_noise_db=float(qa_policy.get("silence_noise_db", -50.0)),
            silence_min_duration=float(qa_policy.get("silence_min_duration_seconds", 1.0)),
        )
        web_path = run_dir / "web/sections" / f"{stem}.mp3"
        _web_preview(
            edit_path,
            web_path,
            str(tts.get("web", {}).get("bitrate", "64k")),
        )
        qa_warnings = validate_edit_wav(edit_metrics, expected_rate=sample_rate)
        qa_warnings.extend(
            validate_ffmpeg_audio(
                ffmpeg_metrics,
                long_silence_seconds=float(qa_policy.get("long_silence_seconds", 3.0)),
                advisory_lufs_min=float(qa_policy.get("advisory_lufs_min", -28.0)),
                advisory_lufs_max=float(qa_policy.get("advisory_lufs_max", -12.0)),
            )
        )
        if edit_metrics["duration_seconds"] < 0.2:
            qa_warnings.append("suspiciously_short")
        warnings.extend(f"{section['id']}:{item}" for item in qa_warnings)

        duration = float(edit_metrics["duration_seconds"])
        generation = float(meta.get("generation_seconds") or 0.0)
        generation_total += generation
        records.append({
            **{key: section[key] for key in (
                "id", "order", "section_key", "kind", "beat_id", "beat_kind",
                "evidence_ids", "source_text", "source_text_sha256",
                "spoken_text", "spoken_text_sha256",
            )},
            "engine": engine,
            "voice": voice,
            "audio_native_file": native_path.relative_to(run_dir).as_posix(),
            "audio_edit_file": edit_path.relative_to(run_dir).as_posix(),
            "audio_web_file": web_path.relative_to(run_dir).as_posix(),
            "web_file_size_bytes": web_path.stat().st_size,
            "start_seconds": round(cursor, 6),
            "end_seconds": round(cursor + duration, 6),
            "duration_seconds": round(duration, 6),
            "generation_seconds": round(generation, 4),
            "real_time_factor": round(generation / duration, 4) if duration > 0 else None,
            "native_audio": native_metrics,
            "edit_audio": edit_metrics,
            "ffmpeg_audio": ffmpeg_metrics,
            "qa": {
                "status": "warn" if qa_warnings else "pass",
                "warnings": qa_warnings,
            },
        })
        cursor += duration
        edit_paths.append(edit_path)

    return records, edit_paths, cursor, generation_total, warnings


def render_episode(
    *,
    episode_dir: Path,
    config_path: Path = Path("config/tts.yaml"),
    engine_override: str | None = None,
    voice_override: str | None = None,
    output_root: Path = Path(".local/tts"),
    repo_root: Path = Path("."),
) -> tuple[Path, dict[str, Any]]:
    config = load_tts_config(config_path)
    tts = config["tts"]
    requested_engine = engine_override or str(tts["engine"])
    requested_voice = voice_override or str(tts["engines"][requested_engine]["voice"])
    pronunciations = dict(tts.get("pronunciation", {}).get("entries") or {})
    sections, raw_sections = load_spoken_sections(
        episode_dir, pronunciations=pronunciations
    )
    script_id = _script_id(episode_dir)
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + f"-{requested_engine}-{script_id[:8]}"
    )
    run_dir = (repo_root / output_root / episode_dir.name / run_id).resolve()

    fallback = tts.get("fallback", {})
    engines = [requested_engine]
    fallback_engine = str(fallback.get("engine") or "")
    if (\n        requested_engine != "edge"\n        and bool(fallback.get("enabled"))\n        and fallback_engine\n        and fallback_engine not in engines\n    ):
        engines.append(fallback_engine)

    errors: list[str] = []
    records: list[dict[str, Any]] = []
    edit_paths: list[Path] = []
    duration = 0.0
    generation_total = 0.0
    qa_warnings: list[str] = []
    used_engine = requested_engine
    used_voice = requested_voice

    for candidate_engine in engines:
        candidate_voice = (
            requested_voice
            if candidate_engine == requested_engine and voice_override
            else str(tts["engines"][candidate_engine]["voice"])
        )
        shutil.rmtree(run_dir, ignore_errors=True)
        try:
            records, edit_paths, duration, generation_total, qa_warnings = (
                _render_sections_with_engine(
                    sections=sections,
                    engine=candidate_engine,
                    voice=candidate_voice,
                    config=config,
                    run_dir=run_dir,
                    repo_root=repo_root,
                )
            )
            used_engine = candidate_engine
            used_voice = candidate_voice
            break
        except (EngineError, subprocess.SubprocessError, OSError) as exc:
            errors.append(f"{candidate_engine}:{exc}")
    else:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise EngineError("All configured TTS engines failed: " + " | ".join(errors))

    warnings = list(qa_warnings)
    if used_engine != requested_engine:
        warnings.insert(0, f"fallback_used:{requested_engine}->{used_engine}")

    master = run_dir / "audio/edit/narration_master.wav"
    _concat_wav(edit_paths, master)
    master_metrics = inspect_wav(master)
    master_warnings = validate_edit_wav(
        master_metrics, expected_rate=int(tts["edit_sample_rate_hz"])
    )
    warnings.extend(f"master:{item}" for item in master_warnings)

    preview = run_dir / "web/narration_preview.mp3"
    _web_preview(master, preview, str(tts.get("web", {}).get("bitrate", "64k")))

    manifest = {
        "schema_version": "1.0",
        "manifest_id": f"tts:{episode_dir.name}:{run_id}",
        "run_id": run_id,
        "script_id": script_id,
        "episode_date": episode_dir.name,
        "generated_at_utc": utc_now(),
        "status": "complete",
        "engine": {
            "requested": requested_engine,
            "used": used_engine,
            "voice": used_voice,
            "language": "es",
            "local_first": used_engine != "edge",
            "network_required": used_engine == "edge",
        },
        "render": {
            "edit_sample_rate_hz": int(tts["edit_sample_rate_hz"]),
            "channels": 1,
            "sample_format": "pcm_s16le",
            "speed": float(tts.get("speech", {}).get("speed", 1.0)),
        },
        "source": {
            "script_path": _repo_relative(episode_dir / "script.txt", repo_root),
            "sections_path": _repo_relative(
                episode_dir / "script_sections.json", repo_root
            ),
            "sections_schema_version": raw_sections.get("schema_version"),
        },
        "files": {
            "master_edit": master.relative_to(run_dir).as_posix(),
            "web_preview": preview.relative_to(run_dir).as_posix(),
        },
        "sections": records,
        "metrics": {
            "section_count": len(records),
            "duration_seconds": round(duration, 6),
            "generation_seconds": round(generation_total, 4),
            "real_time_factor": (
                round(generation_total / duration, 4) if duration > 0 else None
            ),
            "web_preview_size_bytes": preview.stat().st_size,
        },
        "qa": {
            "status": "warn" if warnings else "pass",
            "warnings": warnings,
            "master": master_metrics,
        },
        "errors": errors,
    }
    manifest_path = write_manifest(run_dir / "narration_manifest.json", manifest)
    return manifest_path, manifest
