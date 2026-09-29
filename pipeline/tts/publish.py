from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import validate_benchmark_web_manifest, validate_web_manifest


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


def build_benchmark_web_manifest(
    benchmark: dict[str, Any],
    *,
    common_text: str,
    preview_urls: dict[str, str] | None = None,
) -> dict[str, Any]:
    preview_urls = preview_urls or {}
    candidates: list[dict[str, Any]] = []
    for item in benchmark.get("results", []):
        if not isinstance(item, dict):
            continue
        engine = str(item.get("engine") or "")
        voice = str(item.get("voice") or "")
        key = f"{engine}::{voice}"
        perceptual = item.get("perceptual") if isinstance(item.get("perceptual"), dict) else {}
        candidates.append({
            "engine": engine,
            "voice": voice,
            "status": str(item.get("status") or "error"),
            "error": item.get("error"),
            "generation_seconds": float(item.get("generation_seconds") or 0.0),
            "duration_seconds": float(item.get("duration_seconds") or 0.0),
            "real_time_factor": item.get("real_time_factor"),
            "file_size_bytes": item.get("file_size_bytes"),
            "preview_url": preview_urls.get(key),
            "perceptual": {
                "naturalness": perceptual.get("naturalness"),
                "pronunciation": perceptual.get("pronunciation"),
                "prosody": perceptual.get("prosody"),
                "energy": perceptual.get("energy"),
                "clarity": perceptual.get("clarity"),
                "pace": perceptual.get("pace"),
                "stability": perceptual.get("stability"),
                "notes": perceptual.get("notes"),
            },
        })
    payload = {
        "schema_version": "1.0",
        "available": any(bool(item.get("preview_url")) for item in candidates),
        "generated_at_utc": str(benchmark.get("generated_at_utc") or _utc_now()),
        "fixture": str(benchmark.get("fixture") or "evals/tts/voice_bakeoff_es.txt"),
        "common_text": str(common_text).strip(),
        "candidates": candidates,
    }
    validate_benchmark_web_manifest(payload)
    return payload


def write_benchmark_web_manifest(path: Path, payload: dict[str, Any]) -> Path:
    validate_benchmark_web_manifest(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_url_map(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("URL map must be a JSON object")
    result: dict[str, str] = {}
    for key, value in payload.items():
        if not str(key).strip() or not str(value).strip():
            raise ValueError("URL map entries cannot be empty")
        result[str(key)] = str(value)
    return result
