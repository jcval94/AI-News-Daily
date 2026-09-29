from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.schema_validation import validate_payload


def validate_manifest(payload: dict[str, Any]) -> None:
    validate_payload(payload, "tts/narration_manifest.schema.json")


def write_manifest(path: Path, payload: dict[str, Any]) -> Path:
    validate_manifest(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def validate_web_manifest(payload: dict[str, Any]) -> None:
    validate_payload(payload, "tts/narration_web.schema.json")
