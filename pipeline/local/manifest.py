from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.schema_validation import validate_payload


def new_run_manifest(run_id: str, target_date: str) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "target_date": target_date,
        "status": "running",
        "privacy": {
            "absolute_paths_persisted": False,
            "raw_media_uploaded": False,
        },
        "preflight": {
            "status": "not_run",
            "blockers": [],
            "warnings": [],
        },
        "steps": [],
        "result": {"blockers": [], "warnings": []},
    }
    validate_payload(payload, "local/local_run_manifest.schema.json")
    return payload


def write_run_manifest(path: Path, payload: dict[str, Any]) -> Path:
    validate_payload(payload, "local/local_run_manifest.schema.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
