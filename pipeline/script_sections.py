from __future__ import annotations

import re
from typing import Any


MARKER_RE = re.compile(r"<!--SECTION:(opening|synthesis|beat:[a-z0-9][a-z0-9_-]{0,31})-->")
MEMORY_MARKER_RE = re.compile(r"<!--MEMORY:([a-z0-9][a-z0-9_-]{2,79})-->")


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


def _trim_empty_trailing_markers(
    text: str, matches: list[re.Match[str]], expected: list[str]
) -> tuple[str, list[re.Match[str]]]:
    """Ignore only marker-only debris after a complete valid script.

    Models occasionally echo one internal marker after finishing the synthesis. That
    should not destroy an otherwise valid essay if the suffix contains *no spoken
    text*. Any extra marker with narration remains a hard alignment error.
    """
    if len(matches) <= len(expected):
        return text, matches
    prefix_keys = [match.group(1) for match in matches[: len(expected)]]
    if prefix_keys != expected:
        return text, matches
    extra_start = matches[len(expected)].start()
    suffix = text[extra_start:]
    spoken_suffix = MARKER_RE.sub("", suffix).strip()
    if spoken_suffix:
        return text, matches
    trimmed = text[:extra_start].rstrip()
    return trimmed, list(MARKER_RE.finditer(trimmed))


def parse_sectioned_script(value: str, episode_plan: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    text = str(value or "").strip()
    matches = list(MARKER_RE.finditer(text))
    expected = expected_section_keys(episode_plan)
    if not matches:
        raise SectionAlignmentError("Writer returned no internal section markers")
    if text[: matches[0].start()].strip():
        raise SectionAlignmentError("Narration appeared before the opening section marker")

    text, matches = _trim_empty_trailing_markers(text, matches, expected)
    keys = [match.group(1) for match in matches]
    if keys != expected:
        raise SectionAlignmentError(f"Section markers must be exactly {expected}; got {keys}")

    opening_memory_id = str(episode_plan.get("opening_memory_id", "") or "").strip()
    memory_matches = list(MEMORY_MARKER_RE.finditer(text))
    if not opening_memory_id:
        raise SectionAlignmentError("episode_plan is missing opening_memory_id")
    if len(memory_matches) != 1:
        raise SectionAlignmentError(
            f"Script must contain exactly one Narrative Memory marker; got {len(memory_matches)}"
        )
    if memory_matches[0].group(1) != opening_memory_id:
        raise SectionAlignmentError(
            "Narrative Memory marker must match episode_plan.opening_memory_id"
        )

    beats = _beat_by_key(episode_plan)
    sections: list[dict[str, Any]] = []
    clean_parts: list[str] = []
    memory_metadata: dict[str, Any] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        raw_spoken = text[start:end].strip()
        if not raw_spoken:
            raise SectionAlignmentError(f"Section {match.group(1)} is empty")
        if MARKER_RE.search(raw_spoken):
            raise SectionAlignmentError("Nested section marker detected")
        key = match.group(1)
        section_memory_matches = list(MEMORY_MARKER_RE.finditer(raw_spoken))
        if key != "opening" and section_memory_matches:
            raise SectionAlignmentError("Narrative Memory marker must appear inside opening")
        if key == "opening":
            if len(section_memory_matches) != 1:
                raise SectionAlignmentError(
                    "Opening must contain exactly one Narrative Memory marker"
                )
            marker = section_memory_matches[0]
            words_before_marker = len(
                MEMORY_MARKER_RE.sub("", raw_spoken[: marker.start()]).split()
            )
            if words_before_marker > 120:
                raise SectionAlignmentError(
                    "Narrative Memory marker appears too late in opening "
                    f"({words_before_marker} words; max 120)"
                )
            memory_metadata = {
                "opening_memory_id": opening_memory_id,
                "marker_words_from_opening_start": words_before_marker,
            }
        spoken = MEMORY_MARKER_RE.sub("", raw_spoken).strip()
        if not spoken:
            raise SectionAlignmentError(f"Section {match.group(1)} is empty after metadata removal")
        beat = beats.get(key, {})
        section: dict[str, Any] = {
            "section_key": key,
            "kind": "opening" if key == "opening" else "synthesis" if key == "synthesis" else "development",
            "beat_id": key.split(":", 1)[1] if key.startswith("beat:") else None,
            "beat_kind": beat.get("kind") if beat else None,
            "evidence_ids": list(beat.get("evidence_ids", [])) if beat else [],
            "spoken_text": spoken,
            "word_count": len(spoken.split()),
        }
        sections.append(section)
        clean_parts.append(spoken)

    clean_script = "\n\n".join(clean_parts).strip()
    return clean_script, {
        "schema_version": 3,
        "sections": sections,
        "narrative_memory": memory_metadata,
    }
