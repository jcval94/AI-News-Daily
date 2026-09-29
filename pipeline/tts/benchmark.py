from __future__ import annotations

import json
from pathlib import Path

from .audio_qa import inspect_wav
from .config import load_tts_config
from .engines import render_native
from .render import _convert_edit


def benchmark_voices(*, fixture: Path, output_dir: Path, config_path: Path, repo_root: Path) -> Path:
    config = load_tts_config(config_path)
    text = fixture.read_text(encoding="utf-8").strip()
    output_dir.mkdir(parents=True, exist_ok=True)
    common = output_dir / "benchmark_text.txt"
    common.write_text(text + "\n", encoding="utf-8")
    results = []
    for candidate in config["tts"].get("benchmark", {}).get("candidates", []):
        engine, voice = str(candidate["engine"]), str(candidate["voice"])
        stem = f"{engine}__{voice}".replace("/", "-")
        native = output_dir / "native" / f"{stem}.wav"
        edit = output_dir / "edit" / f"{stem}.wav"
        try:
            meta = render_native(engine=engine, voice=voice, text_file=common, output_file=native, config=config, repo_root=repo_root)
            _convert_edit(native, edit, int(config["tts"]["edit_sample_rate_hz"]))
            metrics = inspect_wav(edit)
            duration = float(metrics["duration_seconds"])
            generation = float(meta.get("generation_seconds") or 0.0)
            status, error = "ok", None
        except Exception as exc:
            metrics, duration, generation = {}, 0.0, 0.0
            status, error = "error", str(exc)
        results.append({
            "engine": engine, "voice": voice, "status": status, "error": error,
            "generation_seconds": generation, "duration_seconds": duration,
            "real_time_factor": round(generation / duration, 4) if duration else None,
            "file_size_bytes": metrics.get("file_size_bytes"),
            "edit_file": edit.relative_to(output_dir).as_posix() if status == "ok" else None,
            "perceptual": {
                "naturalness": None, "pronunciation": None, "prosody": None,
                "energy": None, "clarity": None, "pace": None, "stability": None,
                "notes": "manual listening only"
            },
        })
    report = {
        "schema_version": 1, "fixture": fixture.as_posix(),
        "technical_metrics_are_measured": True,
        "perceptual_scores_are_manual": True, "results": results
    }
    path = output_dir / "benchmark.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
