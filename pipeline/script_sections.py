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


def writer_marker_contract(plan: dict[str, Any]) -> str:
    """Render concrete section IDs so the writer need not infer placement metadata."""
    memory = plan.get('primary_memory_id') or plan.get('opening_memory_id') or ''
    parallel = next((p for p in plan.get('narrative_parallels', []) if p.get('memory_id') == memory), {})
    placement = parallel.get('placement', 'opening')
    sections = expected_section_keys(plan)
    if placement == 'opening': allowed = ['opening']
    elif placement == 'closing_callback': allowed = ['synthesis']
    else:
        allowed = [key for key, beat in _beat_by_key(plan).items() if placement == 'support' or beat.get('kind') == 'turn']
    return ('\nExact SECTION order: ' + ' '.join(f'<!--SECTION:{key}-->' for key in sections) +
            f'\nEmit <!--MEMORY:{memory}--> exactly once in the entire draft, inside ONE of these sections: ' +
            ', '.join(allowed) + '. Never place it in any other section or in an explanation of the format. '
            'Other selected memory records do not receive a MEMORY marker. Do not repeat the marker in a callback.')


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
    primary_memory_id = str(
        episode_plan.get("primary_memory_id") or opening_memory_id or ""
    ).strip()
    if not primary_memory_id:
        raise SectionAlignmentError("episode_plan is missing primary_memory_id")

    parallels = episode_plan.get("narrative_parallels", [])
    parallel = next(
        (
            item
            for item in parallels
            if isinstance(item, dict)
            and str(item.get("memory_id", "") or "").strip() == primary_memory_id
        ),
        None,
    )
    if parallel is None:
        raise SectionAlignmentError(
            "episode_plan.primary_memory_id must reference narrative_parallels"
        )
    planned_placement = str(
        parallel.get("placement")
        or ("opening" if opening_memory_id == primary_memory_id else "narrative_turn")
    ).strip()

    memory_matches = list(MEMORY_MARKER_RE.finditer(text))
    if len(memory_matches) != 1:
        raise SectionAlignmentError(
            f"Script must contain exactly one Narrative Memory marker; got {len(memory_matches)}"
        )
    if memory_matches[0].group(1) != primary_memory_id:
        raise SectionAlignmentError(
            "Narrative Memory marker must match episode_plan.primary_memory_id"
        )

    beats = _beat_by_key(episode_plan)
    sections: list[dict[str, Any]] = []
    clean_parts: list[str] = []
    memory_metadata: dict[str, Any] = {}
    first_evidence_start_word: int | None = None
    cumulative_words = 0

    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        raw_spoken = text[start:end].strip()
        if not raw_spoken:
            raise SectionAlignmentError(f"Section {match.group(1)} is empty")
        if MARKER_RE.search(raw_spoken):
            raise SectionAlignmentError("Nested section marker detected")

        key = match.group(1)
        beat = beats.get(key, {})
        section_memory_matches = list(MEMORY_MARKER_RE.finditer(raw_spoken))
        if len(section_memory_matches) > 1:
            raise SectionAlignmentError(
                f"Section {key} contains more than one Narrative Memory marker"
            )

        if section_memory_matches:
            marker = section_memory_matches[0]
            words_before_marker = len(
                MEMORY_MARKER_RE.sub("", raw_spoken[: marker.start()]).split()
            )
            if planned_placement == "opening":
                if key != "opening":
                    raise SectionAlignmentError(
                        "Narrative Memory planned for opening must appear inside opening"
                    )
                if words_before_marker > 120:
                    raise SectionAlignmentError(
                        "Narrative Memory marker appears too late in opening "
                        f"({words_before_marker} words; max 120)"
                    )
            elif planned_placement == "narrative_turn":
                if not key.startswith("beat:") or beat.get("kind") != "turn":
                    raise SectionAlignmentError(
                        "Narrative Memory planned as narrative_turn must appear inside a turn beat"
                    )
            elif planned_placement == "closing_callback":
                if key != "synthesis":
                    raise SectionAlignmentError(
                        "Narrative Memory planned as closing_callback must appear inside synthesis"
                    )
            elif planned_placement == "support":
                if not key.startswith("beat:"):
                    raise SectionAlignmentError(
                        "Narrative Memory planned as support must appear inside a development beat"
                    )
            else:
                raise SectionAlignmentError(
                    f"Unsupported Narrative Memory placement={planned_placement!r}"
                )

            memory_metadata = {
                "primary_memory_id": primary_memory_id,
                "opening_memory_id": (
                    primary_memory_id if planned_placement == "opening" else None
                ),
                "placement": planned_placement,
                "section_key": key,
                "marker_words_from_section_start": words_before_marker,
            }

        spoken = MEMORY_MARKER_RE.sub("", raw_spoken).strip()
        if not spoken:
            raise SectionAlignmentError(
                f"Section {match.group(1)} is empty after metadata removal"
            )
        evidence_ids = list(beat.get("evidence_ids", [])) if beat else []
        section: dict[str, Any] = {
            "section_key": key,
            "kind": (
                "opening"
                if key == "opening"
                else "synthesis"
                if key == "synthesis"
                else "development"
            ),
            "beat_id": key.split(":", 1)[1] if key.startswith("beat:") else None,
            "beat_kind": beat.get("kind") if beat else None,
            "evidence_ids": evidence_ids,
            "spoken_text": spoken,
            "word_count": len(spoken.split()),
        }
        if first_evidence_start_word is None and evidence_ids:
            first_evidence_start_word = cumulative_words
        sections.append(section)
        clean_parts.append(spoken)
        cumulative_words += section["word_count"]

    if not memory_metadata:
        raise SectionAlignmentError("Narrative Memory marker was not assigned to a section")

    clean_script = "\n\n".join(clean_parts).strip()
    return clean_script, {
        "schema_version": 4,
        "sections": sections,
        "narrative_memory": memory_metadata,
        "first_evidence_start_word": first_evidence_start_word,
    }
