from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


_CONFIG_ROOT = Path(__file__).resolve().parents[1] / "config"


def validate_payload(payload: Any, schema_name: str) -> None:
    schema_path = _CONFIG_ROOT / schema_name
    if not schema_path.is_file():
        raise FileNotFoundError(f"Missing JSON schema: {schema_path}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path))
    if not errors:
        return
    first = errors[0]
    location = ".".join(str(part) for part in first.absolute_path) or "<root>"
    raise ValueError(
        f"Schema validation failed for {schema_name} at {location}: {first.message}"
    )
