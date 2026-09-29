from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = Path("config/tts.yaml")


def load_tts_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or int(payload.get("schema_version", 0)) != 1:
        raise ValueError("TTS config must be a schema_version=1 mapping")
    tts = payload.get("tts")
    if not isinstance(tts, dict):
        raise ValueError("TTS config requires a tts mapping")
    if int(tts.get("edit_sample_rate_hz", 0)) != 48000:
        raise ValueError("TTS edit_sample_rate_hz must be 48000 for the current Resolve contract")
    if str(tts.get("language") or "") != "es":
        raise ValueError("TTS v1 currently requires language=es")
    return payload
