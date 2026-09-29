from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = Path("config/tts.yaml")
_SUPPORTED_ENGINES = {"kokoro", "piper", "edge"}


def load_tts_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or int(payload.get("schema_version", 0)) != 1:
        raise ValueError("TTS config must be a schema_version=1 mapping")
    tts = payload.get("tts")
    if not isinstance(tts, dict):
        raise ValueError("TTS config requires a tts mapping")
    if int(tts.get("edit_sample_rate_hz", 0)) != 48000:
        raise ValueError(
            "TTS edit_sample_rate_hz must be 48000 for the current Resolve contract"
        )
    if str(tts.get("language") or "") != "es":
        raise ValueError("TTS v1 currently requires language=es")

    engines = tts.get("engines")
    if not isinstance(engines, dict):
        raise ValueError("TTS config requires an engines mapping")
    configured_engine = str(tts.get("engine") or "")
    if configured_engine not in _SUPPORTED_ENGINES or configured_engine not in engines:
        raise ValueError(f"Unsupported or unconfigured TTS engine: {configured_engine!r}")
    for engine, engine_config in engines.items():
        if engine not in _SUPPORTED_ENGINES:
            raise ValueError(f"Unknown TTS engine config: {engine!r}")
        if not isinstance(engine_config, dict):
            raise ValueError(f"Engine config must be a mapping: {engine}")
        if not str(engine_config.get("voice") or "").strip():
            raise ValueError(f"Engine {engine} requires a voice")

    speed = float(tts.get("speech", {}).get("speed", 0.0))
    if speed <= 0:
        raise ValueError("TTS speech.speed must be > 0")

    fallback = tts.get("fallback", {})
    if bool(fallback.get("enabled")):
        fallback_engine = str(fallback.get("engine") or "")
        if fallback_engine not in engines:
            raise ValueError("Enabled TTS fallback must reference a configured engine")
        if fallback_engine == "edge":
            raise ValueError("Edge-TTS cannot be configured as automatic fallback")

    qa = tts.get("qa", {})
    lufs_min = float(qa.get("advisory_lufs_min", -28.0))
    lufs_max = float(qa.get("advisory_lufs_max", -12.0))
    if lufs_min >= lufs_max:
        raise ValueError("TTS QA advisory LUFS min must be lower than max")
    if float(qa.get("long_silence_seconds", 3.0)) <= 0:
        raise ValueError("TTS QA long_silence_seconds must be > 0")

    pronunciations = tts.get("pronunciation", {}).get("entries", {})
    if not isinstance(pronunciations, dict):
        raise ValueError("TTS pronunciation.entries must be a mapping")
    if any(not str(key).strip() or not str(value).strip() for key, value in pronunciations.items()):
        raise ValueError("TTS pronunciation entries cannot be empty")
    return payload
