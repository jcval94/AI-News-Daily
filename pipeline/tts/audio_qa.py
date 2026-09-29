from __future__ import annotations

import math
import wave
from array import array
from pathlib import Path
from typing import Any


def inspect_wav(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size <= 44:
        raise ValueError(f"WAV missing or empty: {path}")
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.getnframes()
        raw = wav.readframes(frames)
    if sample_width != 2:
        raise ValueError(f"TTS QA v1 expects 16-bit PCM WAV, got sample_width={sample_width}")
    samples = array("h")
    samples.frombytes(raw)
    if samples.itemsize != 2:
        raise RuntimeError("Unexpected platform int16 representation")
    peak_int = max((abs(value) for value in samples), default=0)
    max_int = 32767.0
    peak = min(1.0, peak_int / max_int) if max_int else 0.0
    square_mean = (sum(float(v) * float(v) for v in samples) / len(samples)) if samples else 0.0
    rms = math.sqrt(square_mean) / max_int if square_mean > 0 else 0.0
    duration = frames / sample_rate if sample_rate else 0.0
    peak_dbfs = 20 * math.log10(peak) if peak > 0 else float("-inf")
    rms_dbfs = 20 * math.log10(rms) if rms > 0 else float("-inf")
    return {
        "file_size_bytes": path.stat().st_size,
        "duration_seconds": round(duration, 6),
        "sample_rate_hz": sample_rate,
        "channels": channels,
        "sample_width_bytes": sample_width,
        "peak_linear": round(peak, 6),
        "peak_dbfs": round(peak_dbfs, 3) if math.isfinite(peak_dbfs) else None,
        "rms_dbfs": round(rms_dbfs, 3) if math.isfinite(rms_dbfs) else None,
        "clipping_suspected": peak >= 0.999,
        "silent_suspected": rms <= 0.0001,
    }


def validate_edit_wav(metrics: dict[str, Any], *, expected_rate: int = 48000) -> list[str]:
    warnings: list[str] = []
    if metrics["duration_seconds"] <= 0:
        warnings.append("zero_duration")
    if metrics["sample_rate_hz"] != expected_rate:
        warnings.append("sample_rate_mismatch")
    if metrics["channels"] != 1:
        warnings.append("unexpected_channels")
    if metrics["clipping_suspected"]:
        warnings.append("clipping_suspected")
    if metrics["silent_suspected"]:
        warnings.append("silence_suspected")
    return warnings
