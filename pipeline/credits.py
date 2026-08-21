from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.licenses import assess_license


def build_credits(manifest: list[dict[str, Any]]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for asset in manifest:
        if not isinstance(asset, dict):
            continue
        decision = assess_license(str(asset.get("provider", "")), str(asset.get("license", "")))
        if not decision["allowed"]:
            raise ValueError(
                f"Asset {asset.get('file', '?')} has a non-publishable license: {decision['reason']}"
            )
        entries.append(
            {
                "shot_number": asset.get("shot_number"),
                "file": asset.get("file", ""),
                "provider": asset.get("provider", ""),
                "creator": asset.get("creator", ""),
                "license": asset.get("license", ""),
                "source_url": asset.get("source_url", ""),
                "requires_attribution": bool(decision["requires_attribution"]),
                "license_reason": decision["reason"],
            }
        )
    return {
        "schema_version": 1,
        "all_assets_license_valid": True,
        "asset_count": len(entries),
        "attribution_required_count": sum(1 for item in entries if item["requires_attribution"]),
        "entries": entries,
    }


def render_credits_markdown(payload: dict[str, Any]) -> str:
    lines = ["# Multimedia credits", "", "Generated from the episode multimedia manifest.", ""]
    entries = payload.get("entries", []) if isinstance(payload, dict) else []
    if not entries:
        lines.append("No external multimedia assets were used.")
        return "\n".join(lines) + "\n"
    for item in entries:
        creator = str(item.get("creator", "") or "Unknown creator")
        license_name = str(item.get("license", "") or "Unknown license")
        source = str(item.get("source_url", "") or "")
        file_name = str(item.get("file", "") or "")
        provider = str(item.get("provider", "") or "")
        lines.append(f"- `{file_name}` — {creator} — {license_name} — {provider}" + (f" — {source}" if source else ""))
    return "\n".join(lines) + "\n"


def write_credits(manifest: list[dict[str, Any]], output_dir: Path) -> tuple[Path, Path]:
    payload = build_credits(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "credits.json"
    md_path = output_dir / "credits.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_credits_markdown(payload), encoding="utf-8")
    return md_path, json_path
