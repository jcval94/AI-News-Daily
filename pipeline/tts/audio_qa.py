from __future__ import annotations

import math
import re
import shutil
import subprocess
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
        raise ValueError(
            f"TTS QA v1 expects 16-bit PCM WAV, got sample_width={sample_width}"
        )
    samples = array("h")
    samples.frombytes(raw)
    if samples.itemsize != 2:
        raise RuntimeError("Unexpected platform int16 representation")
    peak_int = max((abs(value) for value in samples), default=0)
    max_int = 32767.0
    peak = min(1.0, peak_int / max_int) if max_int else 0.0
    square_mean = (
        sum(float(v) * float(v) for v in samples) / len(samples)
        if samples
        else 0.0
    )
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


def inspect_ffmpeg_audio(
    path: Path,
    *,
    silence_noise_db: float = -50.0,
    silence_min_duration: float = 1.0,
) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return {
            "available": False,
            "integrated_lufs": None,
            "true_peak_dbfs": None,
            "silence_events": [],
            "longest_silence_seconds": None,
            "error": "ffmpeg_not_found",
        }
    audio_filter = (
        f"ebur128=peak=true,"
        f"silencedetect=noise={silence_noise_db}dB:d={silence_min_duration}"
    )
    proc = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            audio_filter,
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        check=False,
    )
    stderr = proc.stderr or ""
    if proc.returncode != 0:
        return {
            "available": False,
            "integrated_lufs": None,
            "true_peak_dbfs": None,
            "silence_events": [],
            "longest_silence_seconds": None,
            "error": stderr[-1200:] or f"ffmpeg_exit_{proc.returncode}",
        }

    loudness_hits = re.findall(
        r"(?:^|\s)I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", stderr, flags=re.MULTILINE
    )
    peak_hits = re.findall(
        r"(?:^|\s)Peak:\s*(-?\d+(?:\.\d+)?)\s*dBFS", stderr, flags=re.MULTILINE
    )
    starts = [
        float(value)
        for value in re.findall(r"silence_start:\s*(-?\d+(?:\.\d+)?)", stderr)
    ]
    end_matches = [
        (float(end), float(duration))
        for end, duration in re.findall(
            r"silence_end:\s*(-?\d+(?:\.\d+)?)\s*\|\s*silence_duration:\s*(\d+(?:\.\d+)?)",
            stderr,
        )
    ]
    events: list[dict[str, float | None]] = []
    for index, (end, duration) in enumerate(end_matches):
        start = starts[index] if index < len(starts) else max(0.0, end - duration)
        events.append(
            {
                "start_seconds": round(start, 6),
                "end_seconds": round(end, 6),
                "duration_seconds": round(duration, 6),
            }
        )
    longest = max((float(item["duration_seconds"] or 0.0) for item in events), default=0.0)
    return {
        "available": True,
        "integrated_lufs": float(loudness_hits[-1]) if loudness_hits else None,
        "true_peak_dbfs": float(peak_hits[-1]) if peak_hits else None,
        "silence_events": events,
        "longest_silence_seconds": round(longest, 6),
        "error": None,
    }


def validate_edit_wav(
    metrics: dict[str, Any],
    *,
    expected_rate: int = 48000,
) -> list[str]:
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


def validate_ffmpeg_audio(
    metrics: dict[str, Any],
    *,
    long_silence_seconds: float,
    advisory_lufs_min: float,
    advisory_lufs_max: float,
) -> list[str]:
    if not metrics.get("available"):
        return ["ffmpeg_qa_unavailable"]
    warnings: list[str] = []
    longest = metrics.get("longest_silence_seconds")
    if isinstance(longest, (int, float)) and longest > long_silence_seconds:
        warnings.append("long_silence")
    lufs = metrics.get("integrated_lufs")
    if isinstance(lufs, (int, float)) and not (
        advisory_lufs_min <= lufs <= advisory_lufs_max
    ):
        warnings.append("loudness_outside_advisory_band")
    return warnings
