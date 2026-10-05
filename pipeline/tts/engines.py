from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from time import perf_counter
from typing import Any


class EngineError(RuntimeError):
    pass


def _run(command: list[str], *, timeout: int) -> tuple[float, str]:
    started = perf_counter()
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        shell=False,
        timeout=timeout,
        check=False,
    )
    elapsed = perf_counter() - started
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-3000:]
        raise EngineError(f"TTS command failed ({proc.returncode}): {tail}")
    return elapsed, (proc.stderr or proc.stdout or "")[-3000:]


def resolve_tts_python(config: dict[str, Any], repo_root: Path) -> Path:
    raw = str(config["tts"].get("runtime", {}).get("python") or ".venv-tts/Scripts/python.exe")
    path = Path(raw)
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    return path


def render_native(
    *,
    engine: str,
    voice: str,
    text_file: Path,
    output_file: Path,
    config: dict[str, Any],
    repo_root: Path,
    timeout: int = 600,
) -> dict[str, Any]:
    tts_python = resolve_tts_python(config, repo_root)
    if not tts_python.is_file():
        raise EngineError(f"TTS runtime not found: {tts_python}")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    speed = float(config["tts"].get("speech", {}).get("speed", 1.0))
    local = True
    network_required = False
    native_rate: int | None = None

    if engine == "kokoro":
        command = [str(tts_python), "-m", "kokoro", "-l", "e", "-m", voice, "-s", str(speed), "-i", str(text_file), "-o", str(output_file)]
        native_rate = 24000
    elif engine == "piper":
        model_dir = repo_root / str(config["tts"]["engines"]["piper"].get("model_dir", ".local/models/piper"))
        length_scale = 1.0 / speed if speed > 0 else 1.0
        command = [str(tts_python), "-m", "piper", "--model", voice, "--data-dir", str(model_dir), "--input-file", str(text_file), "--output-file", str(output_file), "--length-scale", str(length_scale)]
    elif engine == "edge":
        local = False
        network_required = True
        mp3_file = output_file.with_suffix(".edge.mp3")
        command = [str(tts_python), "-m", "edge_tts", "--voice", voice, "--text", text_file.read_text(encoding="utf-8"), "--write-media", str(mp3_file)]
        elapsed, log_tail = _run(command, timeout=timeout)
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise EngineError("ffmpeg is required to convert Edge-TTS output")
        _run([ffmpeg, "-y", "-v", "error", "-i", str(mp3_file), "-ac", "1", "-c:a", "pcm_s16le", str(output_file)], timeout=timeout)
        return {"generation_seconds": round(elapsed, 4), "log_tail": log_tail, "local": local, "network_required": network_required, "native_sample_rate_hz": native_rate}
    else:
        raise EngineError(f"Unsupported TTS engine: {engine}")

    elapsed, log_tail = _run(command, timeout=timeout)
    return {"generation_seconds": round(elapsed, 4), "log_tail": log_tail, "local": local, "network_required": network_required, "native_sample_rate_hz": native_rate}
