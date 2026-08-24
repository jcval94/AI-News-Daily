from __future__ import annotations

from typing import Any

from pipeline import review_media as base

DENSE_DEFAULT_MAX_MEDIA = 54
# Keep the candidate cadence compatible with the production floor. A valid minimum
# 420-second episode yields 6 cold-open slots plus at least 40 late slots, so the
# >=45-asset contract remains achievable without relaxing the gate.
POST_OPENING_INTERVAL_SECONDS = 10.0
POST_OPENING_ASSET_SECONDS = 4.5
LATE_VIDEO_EVERY = 3

_QUERY_BASE_BY_KIND = {
    "scene": "researcher working with notes",
    "reflection": "person reviewing research notes",
    "evidence": "scientist laboratory evidence",
    "turn": "scientist analyzing data screen",
    "complication": "researcher investigating data",
    "human_stakes": "person auditing computer screen",
    "reveal": "scientist reviewing findings",
    "historical_mirror": "historical archive documents",
    "concrete_scene": "scientist laboratory experiment",
    "first_reveal": "research evidence laboratory",
    "second_reveal": "scientist research findings",
    "human_peak": "person carefully reviewing evidence",
    "evolved_thesis": "researcher connecting notes and data",
    "payoff": "person reflecting over notes",
    "synthesis": "person reflecting over research evidence",
}
_QUERY_VARIANTS = (
    "close-up documentary b-roll",
    "wide documentary shot",
    "hands working detail",
    "computer screen analysis",
    "team research discussion",
    "equipment and workspace detail",
)


def dense_candidate_slots(section_ranges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create a review storyboard dense enough for an edited video essay, not a sparse gallery.

    Policy:
    - 0–20s: keep the existing ~3.5s video-first cold-open cadence.
    - after 20s: offer one candidate about every 10s across the complete spoken timeline.
    - every candidate remains tied to its section/beat/evidence metadata.
    """
    slots: list[dict[str, Any]] = []
    slot_number = 1
    timeline_end = max(
        (float(item.get("end_seconds", 0) or 0) for item in section_ranges),
        default=base.OPENING_DENSE_MEDIA_SECONDS,
    )
    opening_end = min(base.OPENING_DENSE_MEDIA_SECONDS, timeline_end)

    cursor = 0.0
    while cursor < opening_end:
        end = min(opening_end, cursor + base.OPENING_SLOT_SECONDS)
        if end <= cursor:
            break
        slots.append(
            {
                "slot_number": slot_number,
                "start_seconds": round(cursor, 2),
                "end_seconds": round(end, 2),
                "section_key": "opening",
                "beat_id": "",
                "beat_kind": "opening",
                "evidence_ids": [],
                "slot_priority": "opening_dense_media",
                "preferred_asset_type": "video",
                "motion_preference": "high",
            }
        )
        slot_number += 1
        cursor = end

    for section in section_ranges:
        section_start = max(
            base.OPENING_DENSE_MEDIA_SECONDS,
            float(section.get("start_seconds", 0) or 0),
        )
        section_end = float(section.get("end_seconds", section_start) or section_start)
        if section_end <= section_start:
            continue

        cursor = section_start
        while cursor < section_end:
            end = min(section_end, cursor + POST_OPENING_ASSET_SECONDS)
            if end <= cursor:
                break
            late_index = slot_number - 1
            video_first = late_index % LATE_VIDEO_EVERY == 0
            slots.append(
                {
                    "slot_number": slot_number,
                    "start_seconds": round(cursor, 2),
                    "end_seconds": round(end, 2),
                    "section_key": str(section.get("section_key", "") or ""),
                    "beat_id": str(section.get("beat_id", "") or ""),
                    "beat_kind": str(section.get("beat_kind", "") or ""),
                    "evidence_ids": [str(v) for v in section.get("evidence_ids", [])],
                    "slot_priority": "timeline_cadence",
                    "preferred_asset_type": "video" if video_first else "image_or_video",
                    "motion_preference": "normal",
                }
            )
            slot_number += 1
            cursor += POST_OPENING_INTERVAL_SECONDS

    return slots


def _spread(items: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if count <= 0 or not items:
        return []
    if count >= len(items):
        return list(items)
    if count == 1:
        return [items[len(items) // 2]]
    chosen: list[dict[str, Any]] = []
    used: set[int] = set()
    last = len(items) - 1
    for position in range(count):
        index = round((position * last) / (count - 1))
        while index in used and index < last:
            index += 1
        while index in used and index > 0:
            index -= 1
        if index in used:
            continue
        used.add(index)
        chosen.append(items[index])
    return chosen


def fallback_query(slot: dict[str, Any], ordinal: int) -> str:
    kind = str(slot.get("beat_kind", "") or "").strip().lower()
    section = str(slot.get("section_key", "") or "").strip().lower()
    if section == "synthesis":
        kind = "synthesis"
    evidence = [str(item).strip() for item in slot.get("evidence_ids", []) if str(item).strip()]
    if evidence:
        base_query = "scientist reviewing evidence and research data"
    else:
        base_query = _QUERY_BASE_BY_KIND.get(kind, "researcher notes and computer")
    variant = _QUERY_VARIANTS[ordinal % len(_QUERY_VARIANTS)]
    return f"{base_query}, {variant}"


def dense_media_budget(
    plan: list[dict[str, Any]], *, max_media_downloads: int
) -> list[dict[str, Any]]:
    """Fill the requested media budget across the full timeline before applying the normal cap.

    This intentionally changes the review policy from sparse-per-beat to edited-video cadence.
    It preserves any agent-selected media, fills missing late slots uniformly, and keeps about
    one in three promoted late slots video-first.
    """
    if max_media_downloads <= 0:
        return base.select_spread_media_budget(plan, max_media_downloads=0)

    target = min(max_media_downloads, len(plan))
    current_media = [item for item in plan if item.get("mode") == "media"]
    missing = max(0, target - len(current_media))
    if missing:
        candidates = sorted(
            (
                dict(item)
                for item in plan
                if item.get("mode") != "media"
                and float(item.get("start_seconds", 0) or 0) >= base.OPENING_DENSE_MEDIA_SECONDS
            ),
            key=lambda item: float(item.get("start_seconds", 0) or 0),
        )
        promote = {
            int(item.get("slot_number", 0) or 0): item
            for item in _spread(candidates, min(missing, len(candidates)))
        }
        rewritten: list[dict[str, Any]] = []
        promoted_ordinal = 0
        for item in plan:
            number = int(item.get("slot_number", 0) or 0)
            if number not in promote:
                rewritten.append(item)
                continue
            slot = promote[number]
            video_first = promoted_ordinal % LATE_VIDEO_EVERY == 0
            rewritten.append(
                {
                    **slot,
                    "mode": "media",
                    "visual_query": fallback_query(slot, promoted_ordinal),
                    "on_screen_text": "",
                    "reason": "Dense storyboard cadence: visual support distributed across the full essay",
                    "slot_priority": "timeline_cadence",
                    "preferred_asset_type": "video" if video_first else "image_or_video",
                    "motion_preference": "normal",
                }
            )
            promoted_ordinal += 1
        plan = rewritten

    # Preserve the original guardrails when an agent over-selects the budget.
    return base.select_spread_media_budget(plan, max_media_downloads=max_media_downloads)


def install_density_policy() -> None:
    """Patch the review-media module at runtime while keeping the original implementation as rollback."""
    if getattr(base, "_dense_policy_installed", False):
        return
    original_budget = base.select_spread_media_budget

    def capped_dense_budget(plan: list[dict[str, Any]], *, max_media_downloads: int) -> list[dict[str, Any]]:
        if max_media_downloads <= 0:
            return original_budget(plan, max_media_downloads=0)
        target = min(max_media_downloads, len(plan))
        current = sum(1 for item in plan if item.get("mode") == "media")
        if current < target:
            candidates = sorted(
                (
                    dict(item)
                    for item in plan
                    if item.get("mode") != "media"
                    and float(item.get("start_seconds", 0) or 0) >= base.OPENING_DENSE_MEDIA_SECONDS
                ),
                key=lambda item: float(item.get("start_seconds", 0) or 0),
            )
            selected = {
                int(item.get("slot_number", 0) or 0)
                for item in _spread(candidates, min(target - current, len(candidates)))
            }
            rewritten: list[dict[str, Any]] = []
            ordinal = 0
            for item in plan:
                number = int(item.get("slot_number", 0) or 0)
                if number not in selected:
                    rewritten.append(item)
                    continue
                video_first = ordinal % LATE_VIDEO_EVERY == 0
                rewritten.append(
                    {
                        **item,
                        "mode": "media",
                        "visual_query": fallback_query(item, ordinal),
                        "on_screen_text": "",
                        "reason": "Dense storyboard cadence: visual support distributed across the full essay",
                        "slot_priority": "timeline_cadence",
                        "preferred_asset_type": "video" if video_first else "image_or_video",
                        "motion_preference": "normal",
                    }
                )
                ordinal += 1
            plan = rewritten
        return original_budget(plan, max_media_downloads=max_media_downloads)

    base.build_review_candidate_slots = dense_candidate_slots
    base.select_spread_media_budget = capped_dense_budget
    base._dense_policy_installed = True


def effective_budget(requested: int) -> int:
    """Upgrade the legacy 18-asset workflow default while preserving explicit higher budgets."""
    requested = max(0, int(requested))
    return DENSE_DEFAULT_MAX_MEDIA if requested == 18 else requested
