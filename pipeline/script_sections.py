from __future__ import annotations

import re
from typing import Any


MARKER_RE = re.compile(r"<!--SECTION:(opening|synthesis|beat:[a-z0-9][a-z0-9_-]{0,31})-->")


class SectionAlignmentError(ValueError):
    pass


def expected_section_keys(episode_plan: dict[str, Any]) -> list[str]:
    beats = episode_plan.get("beats", []) if isinstance(episode_plan, dict) else []
    keys = ["opening"]
    for beat in beats:
        if not isinstance(beat, dict):
            raise SectionAlignmentError("episode_plan contains a non-object beat")
        beat_id = str(beat.get("beat_id", "") or "").strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", beat_id):
            raise SectionAlignmentError(f"episode_plan contains invalid beat_id={beat_id!r}")
        keys.append(f"beat:{beat_id}")
    keys.append("synthesis")
    return keys


def _beat_by_key(episode_plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for beat in episode_plan.get("beats", []) if isinstance(episode_plan, dict) else []:
        if isinstance(beat, dict):
            result[f"beat:{beat.get('beat_id', '')}"] = beat
    return result


def parse_sectioned_script(value: str, episode_plan: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    text = str(value or "").strip()
    matches = list(MARKER_RE.finditer(text))
    expected = expected_section_keys(episode_plan)
    if not matches:
        raise SectionAlignmentError("Writer returned no internal section markers")
    if text[: matches[0].start()].strip():
        raise SectionAlignmentError("Narration appeared before the opening section marker")
    keys = [match.group(1) for match in matches]
    if keys != expected:
        raise SectionAlignmentError(f"Section markers must be exactly {expected}; got {keys}")

    beats = _beat_by_key(episode_plan)
    sections: list[dict[str, Any]] = []
    clean_parts: list[str] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        spoken = text[start:end].strip()
        if not spoken:
            raise SectionAlignmentError(f"Section {match.group(1)} is empty")
        if MARKER_RE.search(spoken):
            raise SectionAlignmentError("Nested section marker detected")
        key = match.group(1)
        beat = beats.get(key, {})
        section: dict[str, Any] = {
            "section_key": key,
            "kind": "opening" if key == "opening" else "synthesis" if key == "synthesis" else "development",
            "beat_id": key.split(":", 1)[1] if key.startswith("beat:") else None,
            "beat_kind": beat.get("kind") if beat else None,
            "evidence_news_indices": list(beat.get("evidence_news_indices", [])) if beat else [],
            "spoken_text": spoken,
            "word_count": len(spoken.split()),
        }
        sections.append(section)
        clean_parts.append(spoken)

    clean_script = "\n\n".join(clean_parts).strip()
    return clean_script, {"schema_version": 2, "sections": sections}
