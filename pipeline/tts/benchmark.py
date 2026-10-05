from __future__ import annotations

import html
import json
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
from .engines import render_native
from .render import _convert_edit


def benchmark_status(results: list[dict[str, Any]]) -> str:
    successful = [item for item in results if item.get("status") == "ok"]
    if not successful:
        return "fail"
    if len(successful) != len(results) or any(
        item.get("qa_warnings") for item in successful
    ):
        return "warn"
    return "pass"


def _write_listening_report(
    output_dir: Path,
    results: list[dict[str, Any]],
) -> Path:
    rows = []
    for item in results:
        label = html.escape(f"{item['engine']} / {item['voice']}")
        if item.get("status") == "ok":
            src = html.escape(str(item["edit_file"]), quote=True)
            rows.append(
                f"<li><strong>{label}</strong><br>"
                f"<audio controls preload=\"none\" src=\"{src}\"></audio></li>"
            )
        else:
            error = html.escape(str(item.get("error") or "unknown error"))
            rows.append(f"<li><strong>{label}</strong><br><code>{error}</code></li>")
    path = output_dir / "index.html"
    path.write_text(
        "<!doctype html><meta charset=\"utf-8\"><title>Voice Bake-off</title>"
        "<h1>Voice Bake-off</h1><p>Technical metrics are in benchmark.json. "
        "Perceptual evaluation remains manual.</p><ol>"
        + "".join(rows)
        + "</ol>\n",
        encoding="utf-8",
    )
    return path


def benchmark_voices(
    *,
    fixture: Path,
    output_dir: Path,
    config_path: Path,
    repo_root: Path,
    include_edge: bool = False,
) -> Path:
    config = load_tts_config(config_path)
    qa_policy = config["tts"].get("qa", {})
    text = fixture.read_text(encoding="utf-8").strip()
    output_dir.mkdir(parents=True, exist_ok=True)
    common = output_dir / "benchmark_text.txt"
    common.write_text(text + "\n", encoding="utf-8")
    results = []
    for candidate in config["tts"].get("benchmark", {}).get("candidates", []):
        engine, voice = str(candidate["engine"]), str(candidate["voice"])
        if engine == "edge" and not include_edge:
            continue
        stem = f"{engine}__{voice}".replace("/", "-")
        native = output_dir / "native" / f"{stem}.wav"
        edit = output_dir / "edit" / f"{stem}.wav"
        try:
            meta = render_native(engine=engine, voice=voice, text_file=common, output_file=native, config=config, repo_root=repo_root)
            _convert_edit(native, edit, int(config["tts"]["edit_sample_rate_hz"]))
            metrics = inspect_wav(edit)
            ffmpeg_metrics = inspect_ffmpeg_audio(
                edit,
                silence_noise_db=float(qa_policy.get("silence_noise_db", -50.0)),
                silence_min_duration=float(
                    qa_policy.get("silence_min_duration_seconds", 1.0)
                ),
            )
            qa_warnings = validate_edit_wav(
                metrics,
                expected_rate=int(config["tts"]["edit_sample_rate_hz"]),
            )
            qa_warnings.extend(
                validate_ffmpeg_audio(
                    ffmpeg_metrics,
                    long_silence_seconds=float(
                        qa_policy.get("long_silence_seconds", 3.0)
                    ),
                    advisory_lufs_min=float(
                        qa_policy.get("advisory_lufs_min", -28.0)
                    ),
                    advisory_lufs_max=float(
                        qa_policy.get("advisory_lufs_max", -12.0)
                    ),
                )
            )
            duration = float(metrics["duration_seconds"])
            generation = float(meta.get("generation_seconds") or 0.0)
            status, error = "ok", None
        except Exception as exc:
            metrics, ffmpeg_metrics, qa_warnings = {}, {}, []
            duration, generation = 0.0, 0.0
            status, error = "error", str(exc)
        results.append({
            "engine": engine, "voice": voice, "status": status, "error": error,
            "generation_seconds": generation, "duration_seconds": duration,
            "real_time_factor": round(generation / duration, 4) if duration else None,
            "file_size_bytes": metrics.get("file_size_bytes"),
            "sample_rate_hz": metrics.get("sample_rate_hz"),
            "channels": metrics.get("channels"),
            "sample_width_bytes": metrics.get("sample_width_bytes"),
            "integrated_lufs": ffmpeg_metrics.get("integrated_lufs"),
            "true_peak_dbfs": ffmpeg_metrics.get("true_peak_dbfs"),
            "longest_silence_seconds": ffmpeg_metrics.get("longest_silence_seconds"),
            "qa_warnings": qa_warnings,
            "edit_file": edit.relative_to(output_dir).as_posix() if status == "ok" else None,
            "perceptual": {
                "naturalness": None, "pronunciation": None, "prosody": None,
                "energy": None, "clarity": None, "pace": None, "stability": None,
                "notes": "manual listening only"
            },
        })
    report = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "fixture": fixture.as_posix(),
        "technical_metrics_are_measured": True,
        "perceptual_scores_are_manual": True,
        "status": benchmark_status(results),
        "listening_report": "index.html",
        "results": results,
    }
    _write_listening_report(output_dir, results)
    path = output_dir / "benchmark.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
