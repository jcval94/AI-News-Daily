from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.schema_validation import validate_payload

_TIMESTAMP_TOLERANCE_SECONDS = 0.01


def _validate_section_timestamps(sections: list[dict[str, Any]]) -> None:
    cursor = 0.0
    for expected_order, section in enumerate(sections):
        order = int(section["order"])
        if order != expected_order:
            raise ValueError(
                "Narration section order must be contiguous from zero: "
                f"expected {expected_order}, got {order}"
            )
        start = float(section["start_seconds"])
        end = float(section["end_seconds"])
        duration = float(section["duration_seconds"])
        pause_after = float(section.get("pause_after_seconds", 0.0))
        timeline_end = float(section.get("timeline_end_seconds", end + pause_after))
        if start < 0 or end <= start or duration <= 0:
            raise ValueError(f"Invalid narration timing for section {section['id']!r}")
        if pause_after < 0 or timeline_end < end:
            raise ValueError(f"Invalid narration pause for section {section['id']!r}")
        if abs(start - cursor) > _TIMESTAMP_TOLERANCE_SECONDS:
            raise ValueError(
                f"Narration section {section['id']!r} is not contiguous: "
                f"expected start {cursor:.6f}, got {start:.6f}"
            )
        if abs((end - start) - duration) > _TIMESTAMP_TOLERANCE_SECONDS:
            raise ValueError(
                f"Narration duration mismatch for section {section['id']!r}: "
                f"end-start={end-start:.6f}, duration={duration:.6f}"
            )
        if abs((timeline_end - end) - pause_after) > _TIMESTAMP_TOLERANCE_SECONDS:
            raise ValueError(
                f"Narration pause mismatch for section {section['id']!r}: "
                f"timeline_end-end={timeline_end-end:.6f}, pause={pause_after:.6f}"
            )
        cursor = timeline_end


def validate_manifest(payload: dict[str, Any]) -> None:
    validate_payload(payload, "tts/narration_manifest.schema.json")
    sections = payload.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("Narration manifest requires at least one section")
    _validate_section_timestamps(sections)
    expected_count = int(payload["metrics"]["section_count"])
    if expected_count != len(sections):
        raise ValueError(
            f"Narration section_count mismatch: {expected_count} != {len(sections)}"
        )
    expected_duration = float(payload["metrics"]["duration_seconds"])
    last = sections[-1]
    actual_duration = float(last.get("timeline_end_seconds", last["end_seconds"]))
    if abs(expected_duration - actual_duration) > _TIMESTAMP_TOLERANCE_SECONDS:
        raise ValueError(
            f"Narration total duration mismatch: {expected_duration} != {actual_duration}"
        )


def write_manifest(path: Path, payload: dict[str, Any]) -> Path:
    validate_manifest(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def validate_web_manifest(payload: dict[str, Any]) -> None:
    validate_payload(payload, "tts/narration_web.schema.json")


def validate_benchmark_web_manifest(payload: dict[str, Any]) -> None:
    validate_payload(payload, "tts/benchmark_web.schema.json")
