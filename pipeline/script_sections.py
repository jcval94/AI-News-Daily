from __future__ import annotations

import re
from typing import Any


MARKER_RE = re.compile(r"<!--SECTION:(opening|synthesis|story:\d+)-->")


class SectionAlignmentError(ValueError):
    pass


def expected_section_keys(episode_plan: dict[str, Any]) -> list[str]:
    stories = episode_plan.get("stories", []) if isinstance(episode_plan, dict) else []
    keys = ["opening"]
    for story in stories:
        if not isinstance(story, dict):
            continue
        index = int(story.get("selected_news_index", 0) or 0)
        if index < 1:
            raise SectionAlignmentError("episode_plan contains an invalid selected_news_index")
        keys.append(f"story:{index}")
    keys.append("synthesis")
    return keys


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
        section: dict[str, Any] = {
            "section_key": key,
            "kind": "opening" if key == "opening" else "synthesis" if key == "synthesis" else "development",
            "selected_news_index": int(key.split(":", 1)[1]) if key.startswith("story:") else None,
            "spoken_text": spoken,
            "word_count": len(spoken.split()),
        }
        sections.append(section)
        clean_parts.append(spoken)

    clean_script = "\n\n".join(clean_parts).strip()
    return clean_script, {"schema_version": 1, "sections": sections}
