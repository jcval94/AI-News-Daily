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

    speech = tts.get("speech", {})
    speed = float(speech.get("speed", 0.0))
    if speed <= 0:
        raise ValueError("TTS speech.speed must be > 0")
    pauses = speech.get("pauses", {})
    if not isinstance(pauses, dict):
        raise ValueError("TTS speech.pauses must be a mapping")
    default_ms = float(pauses.get("default_ms", 0.0))
    if default_ms < 0 or default_ms > 5000:
        raise ValueError("TTS speech.pauses.default_ms must be between 0 and 5000")
    after_kind = pauses.get("after_kind_ms", {})
    if not isinstance(after_kind, dict):
        raise ValueError("TTS speech.pauses.after_kind_ms must be a mapping")
    for key, value in after_kind.items():
        if not str(key).strip():
            raise ValueError("TTS pause kind keys cannot be empty")
        numeric = float(value)
        if numeric < 0 or numeric > 5000:
            raise ValueError(
                f"TTS pause for {key!r} must be between 0 and 5000 milliseconds"
            )

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
    if any(
        not str(key).strip() or not str(value).strip()
        for key, value in pronunciations.items()
    ):
        raise ValueError("TTS pronunciation entries cannot be empty")

    web = tts.get("web", {})
    release = web.get("release", {})
    if not isinstance(release, dict):
        raise ValueError("TTS web.release must be a mapping")
    if release:
        if not str(release.get("preview_prefix") or "").strip():
            raise ValueError("TTS web.release.preview_prefix cannot be empty")
        if not str(release.get("benchmark_tag") or "").strip():
            raise ValueError("TTS web.release.benchmark_tag cannot be empty")
        if not str(release.get("target_branch") or "").strip():
            raise ValueError("TTS web.release.target_branch cannot be empty")

    retention = tts.get("retention", {})
    if int(retention.get("pages_episode_audio_limit", 3)) < 1:
        raise ValueError("TTS pages_episode_audio_limit must be >= 1")
    return payload
