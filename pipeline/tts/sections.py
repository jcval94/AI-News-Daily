from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

_HIDDEN = re.compile(r"<!--.*?-->", re.DOTALL)
_HTML_TAG = re.compile(r"</?[A-Za-z][^>]*>")
_MD_LINK = re.compile(r"\[([^\]]+)\]\((?:[^)]+)\)")
_MD_MARK = re.compile(r"(?<!\\)(\*\*|__|~~|`)")
_WS = re.compile(r"[ \t]+")


def normalize_spoken_text(text: str, pronunciations: dict[str, str] | None = None) -> str:
    value = str(text or "")
    value = _HIDDEN.sub("", value)
    value = _HTML_TAG.sub("", value)
    value = _MD_LINK.sub(r"\1", value)
    value = _MD_MARK.sub("", value)
    for source, spoken in (pronunciations or {}).items():
        if source:
            value = re.sub(rf"(?<!\w){re.escape(source)}(?!\w)", str(spoken), value)
    lines = [_WS.sub(" ", line).strip() for line in value.splitlines()]
    value = "\n".join(line for line in lines if line)
    return value.strip()


def safe_section_filename(order: int, section_key: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", section_key.casefold()).strip("-") or "section"
    return f"{order:02d}_{slug[:56]}"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_spoken_sections(
    episode_dir: Path,
    *,
    pronunciations: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = episode_dir / "script_sections.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = payload.get("sections")
    if not isinstance(raw, list) or not raw:
        raise ValueError("script_sections.json contains no sections")
    sections: list[dict[str, Any]] = []
    for order, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"Invalid section at index {order}")
        source = str(item.get("spoken_text") or "").strip()
        spoken = normalize_spoken_text(source, pronunciations)
        if not spoken:
            raise ValueError(f"Section {order} has no pronounceable text")
        section_key = str(item.get("section_key") or f"section-{order}")
        sections.append(
            {
                "id": section_key,
                "order": order,
                "section_key": section_key,
                "kind": str(item.get("kind") or "development"),
                "beat_id": item.get("beat_id"),
                "beat_kind": item.get("beat_kind"),
                "evidence_ids": list(item.get("evidence_ids") or []),
                "source_text": source,
                "source_text_sha256": _sha256_text(source),
                "spoken_text": spoken,
                "spoken_text_sha256": _sha256_text(spoken),
                "filename_stem": safe_section_filename(order, section_key),
            }
        )
    return sections, payload
