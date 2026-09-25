from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pipeline.editing_style import (
    lint_timeline,
    load_editing_style,
    media_defaults,
    public_style_metadata,
)
from pipeline.schema_validation import validate_payload

SCHEMA_VERSION = 1
_EPSILON = 0.02
_DEFAULT_STYLE_PATH = Path(__file__).resolve().parents[1] / "config" / "editing_style.yaml"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _round(value: float) -> float:
    return round(max(0.0, float(value)), 3)


def _script_sha256(script: str) -> str:
    return hashlib.sha256(script.encode("utf-8")).hexdigest()


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").split())


def _validate_script_alignment(script: str, script_sections: dict[str, Any]) -> None:
    sections = script_sections.get("sections", []) if isinstance(script_sections, dict) else []
    if not sections:
        raise ValueError("script_sections.json is required to build edit_manifest.json")
    joined = " ".join(
        str(item.get("spoken_text", "") or "").strip()
        for item in sections
        if isinstance(item, dict)
    )
    if _normalize_text(joined) != _normalize_text(script):
        raise ValueError(
            "script_sections.json narration does not match script.txt; refusing to build a stale edit manifest"
        )


def _section_ranges(
    script_sections: dict[str, Any], words_per_second: float
) -> list[dict[str, Any]]:
    sections = script_sections.get("sections", []) if isinstance(script_sections, dict) else []
    wps = max(0.1, float(words_per_second))
    ranges: list[dict[str, Any]] = []
    cumulative_words = 0
    for position, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        spoken = str(section.get("spoken_text", "") or "").strip()
        words = max(0, int(section.get("word_count", 0) or len(spoken.split())))
        start = cumulative_words / wps
        cumulative_words += words
        end = cumulative_words / wps
        ranges.append(
            {
                "position": position,
                "section_key": str(section.get("section_key", "") or ""),
                "kind": str(section.get("kind", "") or ""),
                "beat_id": section.get("beat_id"),
                "beat_kind": section.get("beat_kind"),
                "evidence_ids": [
                    str(value) for value in section.get("evidence_ids", []) if str(value)
                ],
                "spoken_text": spoken,
                "word_count": words,
                "start_seconds": start,
                "end_seconds": max(start, end),
            }
        )
    return ranges


def _section_at(
    section_ranges: list[dict[str, Any]], timestamp: float
) -> dict[str, Any]:
    if not section_ranges:
        return {}
    for section in section_ranges:
        start = float(section.get("start_seconds", 0) or 0)
        end = float(section.get("end_seconds", start) or start)
        if start - _EPSILON <= timestamp < end + _EPSILON:
            return section
    return section_ranges[-1]


def _excerpt_for_interval(
    section: dict[str, Any], start_seconds: float, end_seconds: float, *, max_words: int = 28
) -> str:
    words = str(section.get("spoken_text", "") or "").split()
    if not words:
        return ""
    section_start = float(section.get("start_seconds", 0) or 0)
    section_end = float(section.get("end_seconds", section_start) or section_start)
    duration = max(section_end - section_start, _EPSILON)
    midpoint = (float(start_seconds) + float(end_seconds)) / 2
    relative = min(1.0, max(0.0, (midpoint - section_start) / duration))
    center = min(len(words) - 1, max(0, round(relative * (len(words) - 1))))
    half = max(4, max_words // 2)
    left = max(0, center - half)
    right = min(len(words), left + max_words)
    left = max(0, right - max_words)
    excerpt = " ".join(words[left:right]).strip()
    if left > 0:
        excerpt = "… " + excerpt
    if right < len(words):
        excerpt += " …"
    return excerpt


def _normalize_media_segments(
    media_plan: dict[str, Any],
    media_manifest: list[dict[str, Any]],
    duration_seconds: float,
) -> tuple[list[dict[str, Any]], list[str]]:
    assets_by_slot: dict[int, dict[str, Any]] = {}
    for item in media_manifest:
        if not isinstance(item, dict):
            continue
        try:
            shot_number = int(item.get("shot_number", 0) or 0)
        except (TypeError, ValueError):
            continue
        if shot_number <= 0:
            continue
        if shot_number in assets_by_slot:
            raise ValueError(f"Duplicate multimedia manifest shot_number={shot_number}")
        assets_by_slot[shot_number] = item

    warnings: list[str] = []
    segments: list[dict[str, Any]] = []
    seen_slots: set[int] = set()
    for item in media_plan.get("segments", []) if isinstance(media_plan, dict) else []:
        if not isinstance(item, dict) or item.get("mode") != "media":
            continue
        try:
            slot_number = int(item.get("slot_number", 0) or 0)
            raw_start = float(item.get("start_seconds", 0) or 0)
            raw_end = float(item.get("end_seconds", 0) or 0)
            start = max(0.0, raw_start)
            end = min(float(duration_seconds), raw_end)
        except (TypeError, ValueError):
            warnings.append("Ignored media cue with invalid slot/timing metadata")
            continue
        if slot_number <= 0 or end <= start + _EPSILON:
            warnings.append(f"Ignored invalid media cue for slot {slot_number}")
            continue
        if slot_number in seen_slots:
            raise ValueError(f"Duplicate media cue slot_number={slot_number}")
        seen_slots.add(slot_number)
        if raw_start < 0 or raw_end > float(duration_seconds) + _EPSILON:
            warnings.append(
                f"Media cue slot {slot_number} was clipped to the estimated script duration"
            )
        asset = assets_by_slot.get(slot_number)
        if asset is None:
            warnings.append(f"Media cue slot {slot_number} has no downloaded asset")
        segments.append(
            {
                **item,
                "slot_number": slot_number,
                "start_seconds": start,
                "end_seconds": end,
                "_asset": asset,
            }
        )

    segments.sort(key=lambda value: (value["start_seconds"], value["end_seconds"], value["slot_number"]))
    previous_end = -1.0
    for item in segments:
        if item["start_seconds"] < previous_end - _EPSILON:
            warnings.append(
                f"Overlapping media cue detected at slot {item['slot_number']}; "
                "edit manifest keeps the earliest cue as timeline authority"
            )
        previous_end = max(previous_end, item["end_seconds"])
    return segments, warnings


def _visual_role(item: dict[str, Any], section: dict[str, Any]) -> str:
    explicit = str(item.get("visual_role", "") or "").strip()
    if explicit:
        return explicit
    priority = str(item.get("slot_priority", "") or "")
    beat_kind = str(section.get("beat_kind", "") or "")
    if priority == "opening_dense_media":
        return "rhythm"
    if priority == "synthesis_payoff":
        return "emotional_grounding"
    if beat_kind == "evidence":
        return "evidence"
    if beat_kind in {"reveal", "turn", "complication"}:
        return "explanation"
    if beat_kind == "human_stakes":
        return "emotional_grounding"
    return "context"


def _treatment(item: dict[str, Any], asset: dict[str, Any] | None) -> str:
    explicit = str(item.get("treatment", "") or "").strip()
    if explicit:
        return explicit
    asset_type = str((asset or {}).get("asset_type", "") or "").strip()
    preferred = str(item.get("preferred_asset_type", "") or "").strip()
    motion = str(item.get("motion_preference", "") or "normal")
    if asset_type == "video" or (not asset_type and preferred == "video"):
        return "natural_motion"
    if motion == "high":
        return "slow_push_in"
    if motion == "low":
        return "static"
    return "subtle_push_in"


def _media_director_signal(
    item: dict[str, Any],
    section: dict[str, Any],
    asset: dict[str, Any] | None,
    editing_style: dict[str, Any] | None,
) -> dict[str, Any]:
    priority = str(item.get("slot_priority", "") or "")
    default_pacing = "fast" if priority == "opening_dense_media" else "normal"
    note = str(item.get("director_note", "") or "").strip()
    if not note:
        note = str(item.get("reason", "") or "").strip()

    role = _visual_role(item, section)
    asset_type = str((asset or {}).get("asset_type", "") or "").strip()
    if not asset_type:
        asset_type = str(item.get("preferred_asset_type", "") or "").strip()
    defaults = media_defaults(editing_style, role=role, asset_type=asset_type)
    transition_default = str(defaults.get("transition", "") or "hard_cut")
    treatment_default = str(defaults.get("treatment", "") or _treatment(item, asset))

    return {
        "authority": "suggestion",
        "priority": "high" if priority in {"opening_dense_media", "synthesis_payoff"} else "normal",
        "intent": str(item.get("reason", "") or "").strip() or "Support the spoken idea with a concrete visual.",
        "visual_role": role,
        "transition_in": str(item.get("transition_in", "") or transition_default),
        "transition_out": str(item.get("transition_out", "") or transition_default),
        "treatment": str(item.get("treatment", "") or treatment_default),
        "pacing": str(item.get("pacing", "") or default_pacing),
        "return_to_presenter": bool(item.get("return_to_presenter", True)),
        "note": note,
    }


def _presenter_director_signal(
    *,
    first: bool,
    after_media: bool,
    editing_style: dict[str, Any] | None,
) -> dict[str, Any]:
    presenter_style = (
        editing_style.get("presenter", {})
        if isinstance(editing_style, dict) and isinstance(editing_style.get("presenter"), dict)
        else {}
    )
    treatment = str(presenter_style.get("default_treatment", "") or "clean_a_roll")
    return {
        "authority": "suggestion",
        "priority": "baseline",
        "intent": "Keep the narrator as the visual continuity and let the face carry the argument.",
        "visual_role": "presenter",
        "transition_in": "none" if first else ("hard_cut" if after_media else "none"),
        "transition_out": "none",
        "treatment": treatment,
        "pacing": "normal",
        "return_to_presenter": False,
        "note": "Stay on camera by default; cover only when another cue materially adds evidence, explanation, context, or rhythm.",
    }


def _asset_payload(asset: dict[str, Any] | None, cue: dict[str, Any]) -> dict[str, Any] | None:
    if asset is None:
        return {
            "available": False,
            "usable_for_edit": False,
            "file_exists": False,
            "blockers": ["missing_manifest_asset"],
            "file": "",
            "asset_type": "",
            "preferred_asset_type": str(cue.get("preferred_asset_type", "") or "image_or_video"),
            "visual_query": str(cue.get("visual_query", "") or ""),
            "on_screen_text": str(cue.get("on_screen_text", "") or ""),
        }

    file_path = str(asset.get("file", "") or "").strip()
    file_exists = asset.get("_file_exists")
    license_valid = bool(asset.get("license_valid", False))
    blockers: list[str] = []
    if not file_path:
        blockers.append("missing_file_path")
    if file_exists is False:
        blockers.append("missing_file")
    if not license_valid:
        blockers.append("license_not_validated")

    return {
        "available": bool(file_path),
        "usable_for_edit": bool(file_path) and file_exists is not False and license_valid,
        "file_exists": file_exists,
        "blockers": blockers,
        "file": file_path,
        "asset_type": str(asset.get("asset_type", "") or ""),
        "preferred_asset_type": str(
            cue.get("preferred_asset_type", "") or asset.get("asset_type", "") or "image_or_video"
        ),
        "mime_type": str(asset.get("mime_type", "") or ""),
        "provider": str(asset.get("provider", "") or ""),
        "source_url": str(asset.get("source_url", "") or ""),
        "creator": str(asset.get("creator", "") or ""),
        "license": str(asset.get("license", "") or ""),
        "license_valid": license_valid,
        "requires_attribution": bool(asset.get("requires_attribution", False)),
        "visual_query": str(cue.get("visual_query", "") or asset.get("visual_query", "") or ""),
        "on_screen_text": str(cue.get("on_screen_text", "") or asset.get("on_screen_text", "") or ""),
        "relevance_score": asset.get("relevance_score"),
        "errors": list(asset.get("errors", []) or []),
    }


def build_edit_manifest(
    *,
    episode_date: str,
    script: str,
    script_sections: dict[str, Any],
    media_plan: dict[str, Any],
    media_manifest: list[dict[str, Any]],
    words_per_second: float,
    source_paths: dict[str, str] | None = None,
    editing_style: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_script_alignment(script, script_sections)
    ranges = _section_ranges(script_sections, words_per_second)
    duration = float(ranges[-1].get("end_seconds", 0) or 0)

    plan_date = str(media_plan.get("script_date", "") or "").strip() if isinstance(media_plan, dict) else ""
    if plan_date and plan_date != str(episode_date):
        raise ValueError(
            f"multimedia plan script_date={plan_date} does not match episode_date={episode_date}"
        )

    cues, warnings = _normalize_media_segments(media_plan, media_manifest, duration)
    planned_duration = media_plan.get("timeline_duration_seconds") if isinstance(media_plan, dict) else None
    if planned_duration not in (None, ""):
        try:
            delta = abs(float(planned_duration) - duration)
        except (TypeError, ValueError):
            warnings.append("Multimedia plan has invalid timeline_duration_seconds")
        else:
            if delta > max(2.0, duration * 0.02):
                warnings.append(
                    "Multimedia plan duration differs materially from current script timing; "
                    "recording retime is mandatory before automated placement"
                )

    boundaries = {0.0, duration}
    for section in ranges:
        boundaries.add(float(section.get("start_seconds", 0) or 0))
        boundaries.add(float(section.get("end_seconds", 0) or 0))
    for cue in cues:
        boundaries.add(float(cue["start_seconds"]))
        boundaries.add(float(cue["end_seconds"]))
    points = sorted(value for value in boundaries if 0.0 <= value <= duration)

    timeline: list[dict[str, Any]] = []
    last_mode = ""
    for start, end in zip(points, points[1:]):
        if end <= start + _EPSILON:
            continue
        midpoint = (start + end) / 2
        section = _section_at(ranges, midpoint)
        active = next(
            (
                cue
                for cue in cues
                if float(cue["start_seconds"]) - _EPSILON <= midpoint < float(cue["end_seconds"]) + _EPSILON
            ),
            None,
        )
        mode = "media" if active else "presenter"
        if active:
            asset = active.get("_asset")
            director = _media_director_signal(active, section, asset, editing_style)
            media = _asset_payload(asset, active)
            cue_id = f"slot_{int(active.get('slot_number', 0)):03d}"
        else:
            asset = None
            director = _presenter_director_signal(
                first=not timeline,
                after_media=last_mode == "media",
                editing_style=editing_style,
            )
            media = None
            cue_id = None

        timeline.append(
            {
                "segment_id": f"seg_{len(timeline) + 1:03d}",
                "mode": mode,
                "start_seconds": _round(start),
                "end_seconds": _round(end),
                "duration_seconds": _round(end - start),
                "cue_id": cue_id,
                "section": {
                    "section_key": str(section.get("section_key", "") or ""),
                    "kind": str(section.get("kind", "") or ""),
                    "beat_id": section.get("beat_id"),
                    "beat_kind": section.get("beat_kind"),
                    "evidence_ids": list(section.get("evidence_ids", []) or []),
                },
                "script_anchor": {
                    "mode": "estimated_word_timing",
                    "excerpt": _excerpt_for_interval(section, start, end),
                },
                "director": director,
                "media": media,
            }
        )
        last_mode = mode

    paths = source_paths or {}
    style_warnings = (
        lint_timeline(timeline, editing_style, duration_seconds=duration)
        if editing_style
        else []
    )
    media_items = [item for item in timeline if item["mode"] == "media"]
    cue_status: dict[str, bool] = {}
    cue_blockers: set[str] = set()
    for item in media_items:
        cue_id = str(item.get("cue_id", "") or "")
        media = item.get("media") if isinstance(item.get("media"), dict) else {}
        if cue_id:
            cue_status[cue_id] = bool(media.get("usable_for_edit") is True)
        for blocker in media.get("blockers", []) if isinstance(media, dict) else []:
            if blocker:
                cue_blockers.add(str(blocker))

    return {
        "schema_version": SCHEMA_VERSION,
        "episode_date": str(episode_date),
        "status": "pre_recording",
        "timing": {
            "basis": "estimated_script_words",
            "words_per_second": float(words_per_second),
            "duration_seconds": _round(duration),
            "requires_recording_retime": True,
            "warning": (
                "Timeline positions are editorial estimates until real A-roll is ingested and aligned. "
                "Do not treat these timestamps as frame-accurate."
            ),
        },
        "sources": {
            "script": paths.get("script", f"scripts/{episode_date}/script.txt"),
            "script_sections": paths.get(
                "script_sections", f"scripts/{episode_date}/script_sections.json"
            ),
            "media_plan": paths.get("media_plan", f"multimedia/{episode_date}/plan.json"),
            "media_manifest": paths.get(
                "media_manifest", f"multimedia/{episode_date}/manifest.json"
            ),
            "script_sha256": _script_sha256(script),
        },
        "editing_defaults": {
            "base_visual": "presenter",
            "director_signal_authority": "suggestion",
            "tracks": {
                "presenter": "V1",
                "b_roll": "V2",
                "graphics": "V3",
                "titles": "V4",
            },
            "principle": (
                "Presenter is visual continuity. Cut away only when media adds evidence, explanation, "
                "context, emotional grounding, analogy, contrast, or intentional rhythm."
            ),
        },
        "editing_style": (
            public_style_metadata(editing_style)
            if editing_style
            else {"applied": False}
        ),
        "style_warnings": style_warnings,
        "readiness": {
            "pre_recording_contract_valid": True,
            "ready_for_recording": True,
            "asset_resolution_complete": bool(cues) and all(cue_status.values()),
            "ready_for_automated_timeline_import": False,
            "blockers": sorted(
                {"recording_retime_required", *cue_blockers}
            ),
        },
        "summary": {
            "segment_count": len(timeline),
            "media_segment_count": sum(1 for item in timeline if item["mode"] == "media"),
            "presenter_segment_count": sum(1 for item in timeline if item["mode"] == "presenter"),
            "media_cue_count": len(cues),
            "manifest_asset_record_count": len(
                [item for item in media_manifest if isinstance(item, dict)]
            ),
            "resolved_media_cue_count": sum(1 for usable in cue_status.values() if usable),
            "blocked_media_cue_count": sum(1 for usable in cue_status.values() if not usable),
        },
        "validation_warnings": warnings,
        "timeline": timeline,
    }


def write_edit_manifest(
    *,
    episode_dir: Path,
    media_dir: Path,
    words_per_second: float,
    editing_style_path: Path | None = None,
) -> Path:
    script = _read_text(episode_dir / "script.txt")
    if not script:
        raise FileNotFoundError(f"Missing or empty script: {episode_dir / 'script.txt'}")
    script_sections = _read_json(episode_dir / "script_sections.json", {})
    media_plan = _read_json(media_dir / "plan.json", {})
    media_manifest = _read_json(media_dir / "manifest.json", [])
    if not isinstance(media_manifest, list):
        raise ValueError("multimedia manifest must be a JSON array")

    verified_manifest: list[dict[str, Any]] = []
    media_root = media_dir.resolve()
    for item in media_manifest:
        if not isinstance(item, dict):
            verified_manifest.append(item)
            continue
        record = dict(item)
        relative = str(record.get("file", "") or "").strip()
        if relative:
            candidate = (media_dir / relative).resolve()
            try:
                candidate.relative_to(media_root)
            except ValueError as exc:
                raise ValueError(f"Multimedia asset escapes media directory: {relative}") from exc
            record["_file_exists"] = candidate.is_file()
        else:
            record["_file_exists"] = False
        verified_manifest.append(record)

    state = _read_json(episode_dir / "run_state.json", {})
    episode_date = str(state.get("episode_date", "") or episode_dir.name)
    style = load_editing_style(editing_style_path or _DEFAULT_STYLE_PATH)
    payload = build_edit_manifest(
        episode_date=episode_date,
        script=script,
        script_sections=script_sections,
        media_plan=media_plan,
        media_manifest=verified_manifest,
        words_per_second=words_per_second,
        editing_style=style,
    )
    validate_payload(payload, "edit_manifest.schema.json")
    destination = media_dir / "edit_manifest.json"
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination
