from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import validate_web_manifest


def build_web_manifest(
    narration_manifest: dict[str, Any],
    *,
    master_url: str | None = None,
    section_urls: dict[str, str] | None = None,
) -> dict[str, Any]:
    section_urls = section_urls or {}
    sections = []
    for item in narration_manifest.get("sections", []):
        sections.append({
            "id": item["id"], "order": item["order"], "kind": item["kind"],
            "duration_seconds": item["duration_seconds"],
            "preview_url": section_urls.get(str(item["id"])),
        })
    payload = {
        "schema_version": "1.0",
        "available": bool(master_url),
        "episode_date": narration_manifest["episode_date"],
        "script_id": narration_manifest["script_id"],
        "generated_at_utc": narration_manifest["generated_at_utc"],
        "engine": narration_manifest["engine"]["used"],
        "voice": narration_manifest["engine"]["voice"],
        "duration_seconds": narration_manifest["metrics"]["duration_seconds"],
        "section_count": narration_manifest["metrics"]["section_count"],
        "qa_status": narration_manifest["qa"]["status"],
        "warnings": list(narration_manifest["qa"].get("warnings") or []),
        "master_preview_url": master_url,
        "sections": sections,
    }
    validate_web_manifest(payload)
    return payload


def write_web_manifest(path: Path, payload: dict[str, Any]) -> Path:
    validate_web_manifest(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
