from __future__ import annotations

import argparse
import asyncio
import json
import re
import unicodedata
import zipfile
from pathlib import Path
from typing import Any

from app.agent import MultimediaPlan, multimedia_editor_agent
from pipeline.core import PipelineConfig, timeline_duration_seconds
from pipeline.credits import write_credits
from pipeline.media import download_shot_asset, download_video_shot_asset
from pipeline.run import normalize_multimedia_plan, run_agent, write_json

CONFIG = PipelineConfig.from_env()
OPENING_DENSE_MEDIA_SECONDS = 20.0
OPENING_MIN_MEDIA_SLOTS = 5
OPENING_SLOT_SECONDS = 3.5
MAX_SECTION_CANDIDATES = 2


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def slug(value: Any, *, fallback: str = "none", limit: int = 64) -> str:
    text = str(value or "").strip().lower()
    text = "".join(
        char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char)
    )
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return (text or fallback)[:limit].rstrip("-")


def section_timeline(script_sections: dict[str, Any], words_per_second: float) -> list[dict[str, Any]]:
    sections = script_sections.get("sections", []) if isinstance(script_sections, dict) else []
    timeline: list[dict[str, Any]] = []
    cumulative_words = 0
    for position, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        spoken = str(section.get("spoken_text", "") or "").strip()
        words = int(section.get("word_count", 0) or len(spoken.split()))
        start = cumulative_words / words_per_second
        cumulative_words += max(0, words)
        end = cumulative_words / words_per_second
        timeline.append(
            {
                "position": position,
                "section_key": str(section.get("section_key", "") or ""),
                "beat_id": str(section.get("beat_id", "") or ""),
                "beat_kind": str(section.get("beat_kind", "") or ""),
                "evidence_ids": [str(v) for v in section.get("evidence_ids", [])],
                "start_seconds": start,
                "end_seconds": max(start, end),
            }
        )
    return timeline


def build_review_candidate_slots(section_ranges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Offer a dense video-first cold open plus sparse idea-led slots later in the essay."""
    slots: list[dict[str, Any]] = []
    slot_number = 1
    opening_end = OPENING_DENSE_MEDIA_SECONDS
    if section_ranges:
        opening_end = min(
            OPENING_DENSE_MEDIA_SECONDS,
            max(0.0, float(section_ranges[-1].get("end_seconds", OPENING_DENSE_MEDIA_SECONDS) or OPENING_DENSE_MEDIA_SECONDS)),
        )

    start = 0.0
    while start < opening_end:
        end = min(opening_end, start + OPENING_SLOT_SECONDS)
        if end <= start:
            break
        slots.append(
            {
                "slot_number": slot_number,
                "start_seconds": round(start, 2),
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
        start = end

    for section in section_ranges:
        key = str(section.get("section_key", "") or "")
        if key == "opening":
            continue
        start = float(section.get("start_seconds", 0) or 0)
        end = float(section.get("end_seconds", start) or start)
        duration = max(0.0, end - start)
        if duration <= 0:
            continue
        if key == "synthesis":
            fractions = (0.55,)
        elif duration >= 28:
            fractions = (0.30, 0.72)
        else:
            fractions = (0.52,)
        for fraction in fractions[:MAX_SECTION_CANDIDATES]:
            midpoint = start + (duration * fraction)
            candidate_start = max(start, midpoint - 2.0)
            candidate_end = min(end, candidate_start + 4.0)
            if candidate_end <= candidate_start:
                continue
            slots.append(
                {
                    "slot_number": slot_number,
                    "start_seconds": round(candidate_start, 2),
                    "end_seconds": round(candidate_end, 2),
                    "section_key": key,
                    "beat_id": section.get("beat_id", ""),
                    "beat_kind": section.get("beat_kind", ""),
                    "evidence_ids": section.get("evidence_ids", []),
                    "slot_priority": "section_focus",
                    "preferred_asset_type": "image_or_video",
                    "motion_preference": "normal",
                }
            )
            slot_number += 1
    return slots


def section_for_time(timeline: list[dict[str, Any]], start: float, end: float) -> dict[str, Any]:
    midpoint = (float(start) + float(end)) / 2.0
    for section in timeline:
        if float(section["start_seconds"]) <= midpoint <= float(section["end_seconds"]):
            return section
    if timeline:
        return min(
            timeline,
            key=lambda section: abs(
                midpoint - ((float(section["start_seconds"]) + float(section["end_seconds"])) / 2.0)
            ),
        )
    return {
        "position": 0,
        "section_key": "unmapped",
        "beat_id": "",
        "beat_kind": "",
        "evidence_ids": [],
    }


def association_label(section: dict[str, Any]) -> str:
    key = str(section.get("section_key", "") or "")
    if key == "opening":
        prefix = "B00_opening"
    elif key == "synthesis":
        prefix = "B99_synthesis"
    else:
        position = int(section.get("position", 0) or 0)
        beat_id = slug(section.get("beat_id") or key, fallback="beat")
        prefix = f"B{position:02d}_{beat_id}"
    evidence = [slug(item) for item in section.get("evidence_ids", []) if str(item).strip()]
    return f"{prefix}__E_{'+'.join(evidence) if evidence else 'none'}"


def media_filename(segment: dict[str, Any], *, extension: str = ".jpg") -> str:
    slot = int(segment.get("slot_number", 0) or 0)
    start = int(round(float(segment.get("start_seconds", 0) or 0)))
    end = int(round(float(segment.get("end_seconds", 0) or 0)))
    label = slug(segment.get("on_screen_text") or segment.get("visual_query"), fallback="visual", limit=48)
    return f"S{slot:03d}__{start:04d}-{end:04d}s__{label}{extension}"


def _opening_fallback_query(index: int) -> str:
    queries = [
        "cinematic close-up of hands highlighting research notes, documentary b-roll",
        "moving archival documents and handwritten notes on a desk, reflective research footage",
        "investigative evidence wall with notes and connecting lines, cinematic b-roll",
        "abstract flowing data traces and light paths, cinematic technology footage",
        "person carefully reviewing papers and a computer screen, documentary footage",
        "close-up hands sorting research notes and printed articles, dynamic b-roll",
    ]
    return queries[index % len(queries)]


def enforce_opening_dense_media(
    plan: list[dict[str, Any]],
    candidate_slots: list[dict[str, Any]],
    *,
    max_media_downloads: int,
) -> list[dict[str, Any]]:
    """Guarantee a dense first 20s cold open even when the planner under-selects it."""
    by_slot = {int(item.get("slot_number", 0) or 0): dict(item) for item in plan}
    slot_meta = {int(item.get("slot_number", 0) or 0): item for item in candidate_slots}
    opening_numbers = [
        number for number, slot in slot_meta.items()
        if float(slot.get("start_seconds", 0) or 0) < OPENING_DENSE_MEDIA_SECONDS
    ]
    opening_numbers.sort()
    if not opening_numbers or max_media_downloads <= 0:
        return [by_slot[number] for number in sorted(by_slot)]

    required = min(OPENING_MIN_MEDIA_SLOTS, len(opening_numbers), max_media_downloads)
    current_opening = [number for number in opening_numbers if by_slot.get(number, {}).get("mode") == "media"]
    if len(current_opening) >= required:
        return [by_slot[number] for number in sorted(by_slot)]

    total_media = sum(1 for item in by_slot.values() if item.get("mode") == "media")
    late_media = [
        int(item.get("slot_number", 0) or 0)
        for item in sorted(
            by_slot.values(),
            key=lambda value: float(value.get("start_seconds", 0) or 0),
            reverse=True,
        )
        if item.get("mode") == "media" and int(item.get("slot_number", 0) or 0) not in opening_numbers
    ]

    for index, number in enumerate(opening_numbers):
        if by_slot.get(number, {}).get("mode") == "media":
            continue
        while total_media >= max_media_downloads and late_media:
            demote = late_media.pop(0)
            by_slot[demote] = {
                **by_slot[demote],
                "mode": "presenter",
                "visual_query": "",
                "on_screen_text": "",
                "reason": "Media budget reallocated to the first 20 seconds cold open",
            }
            total_media -= 1
        if total_media >= max_media_downloads:
            break
        meta = slot_meta[number]
        by_slot[number] = {
            **by_slot[number],
            "mode": "media",
            "visual_query": _opening_fallback_query(index),
            "on_screen_text": "",
            "reason": "Dense cold open: high-motion multimedia in the first 20 seconds",
            "slot_priority": "opening_dense_media",
            "preferred_asset_type": "video",
            "motion_preference": "high",
            "start_seconds": meta.get("start_seconds"),
            "end_seconds": meta.get("end_seconds"),
        }
        total_media += 1
        current_opening.append(number)
        if len(current_opening) >= required:
            break
    return [by_slot[number] for number in sorted(by_slot)]


def write_bundle_readme(output_dir: Path, *, target_date: str, manifest: list[dict[str, Any]]) -> None:
    lines = [
        f"# Review multimedia — {target_date}",
        "",
        "This bundle is for editorial review only; it does not imply episode approval.",
        "",
        "Cold-open rule: the first 20 seconds prioritize motion/video with cuts every ~3–4 seconds.",
        "",
        "Folders are associated to narrative beats, not news order:",
        "`B##_beat-id__E_evidence-id/...`.",
        "",
        "Each filename contains the candidate slot and approximate seconds:",
        "`S###__start-end__description.ext`.",
        "",
        f"Assets: {len(manifest)}",
        "",
    ]
    for item in manifest:
        lines.append(
            f"- `{item.get('file', '')}` — {item.get('asset_type', 'image')} — {item.get('provider', '')}; "
            f"license: {item.get('license', '')}; relevance: {item.get('relevance_score')}"
        )
    (output_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def create_zip(source_dir: Path, zip_path: Path) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file() and path.resolve() != zip_path.resolve():
                archive.write(path, path.relative_to(source_dir.parent))
    return zip_path


async def build_review_media(
    *,
    episode_dir: Path,
    output_dir: Path,
    max_media_downloads: int,
    zip_path: Path,
) -> dict[str, Any]:
    script_path = episode_dir / "script.txt"
    if not script_path.exists():
        raise FileNotFoundError(f"Missing script: {script_path}")
    script = script_path.read_text(encoding="utf-8").strip()
    episode_plan = read_json(episode_dir / "episode_plan.json", {})
    script_sections = read_json(episode_dir / "script_sections.json", {})
    if not episode_plan.get("beats"):
        raise ValueError("episode_plan.json has no idea-led beats")
    if not script_sections.get("sections"):
        raise ValueError("script_sections.json is required for beat/media association")

    output_dir.mkdir(parents=True, exist_ok=True)
    timeline_duration = timeline_duration_seconds(script, CONFIG)
    section_ranges = section_timeline(script_sections, CONFIG.words_per_second)
    timeline_slots = build_review_candidate_slots(section_ranges)
    if not timeline_slots:
        raise ValueError("Could not build review-media candidate slots from script sections")

    trace: list[dict[str, Any]] = []
    editor_state = await run_agent(
        multimedia_editor_agent,
        {
            "final_script": script,
            "episode_plan": json.dumps(episode_plan, ensure_ascii=False),
            "timeline_slots": json.dumps(timeline_slots, ensure_ascii=False),
            "max_media_downloads": max(0, max_media_downloads),
            "opening_dense_media_seconds": OPENING_DENSE_MEDIA_SECONDS,
            "opening_min_media_slots": OPENING_MIN_MEDIA_SLOTS,
        },
        (
            "Plan review multimedia across the FULL essay. The first 20 seconds are a high-energy cold open: "
            "use multimedia in at least five opening slots, prefer motion/video footage, and change visuals every ~3–4 seconds. "
            "After 20 seconds, become selective: use at most two assets in a beat and only when the visual materially explains, "
            "grounds or intensifies the idea. Prefer documentary/explanatory visuals over generic stock metaphors."
        ),
        step="review_plan_multimedia",
        trace=trace,
    )
    raw_plan = MultimediaPlan.model_validate(editor_state.get("multimedia_plan", {})).model_dump()
    normalized, warnings = normalize_multimedia_plan(raw_plan, timeline_slots, max(0, max_media_downloads))
    normalized = enforce_opening_dense_media(
        normalized,
        timeline_slots,
        max_media_downloads=max(0, max_media_downloads),
    )
    slot_meta = {int(slot["slot_number"]): slot for slot in timeline_slots}

    selected_segments: list[dict[str, Any]] = []
    manifest: list[dict[str, Any]] = []
    for segment in normalized:
        if segment.get("mode") != "media":
            continue
        slot_number = int(segment.get("slot_number", 0) or 0)
        meta = slot_meta.get(slot_number, {})
        segment = {
            **segment,
            "slot_priority": segment.get("slot_priority") or meta.get("slot_priority", "section_focus"),
            "preferred_asset_type": segment.get("preferred_asset_type") or meta.get("preferred_asset_type", "image_or_video"),
            "motion_preference": segment.get("motion_preference") or meta.get("motion_preference", "normal"),
        }
        section = section_for_time(
            section_ranges,
            float(segment.get("start_seconds", 0) or 0),
            float(segment.get("end_seconds", 0) or 0),
        )
        folder = association_label(section)
        preferred_video = segment.get("preferred_asset_type") == "video"
        record: dict[str, Any] | None = None
        relative_file = ""
        if preferred_video:
            video_name = media_filename(segment, extension=".mp4")
            video_destination = output_dir / folder / video_name
            video_relative = str(video_destination.relative_to(output_dir)).replace("\\", "/")
            record = download_video_shot_asset(
                {
                    "shot_number": slot_number,
                    "visual_query": segment["visual_query"],
                    "on_screen_text": segment.get("on_screen_text", ""),
                },
                video_destination,
                logical_file=video_relative,
            )
            if record:
                relative_file = video_relative

        if record is None:
            image_name = media_filename(segment, extension=".jpg")
            image_destination = output_dir / folder / image_name
            image_relative = str(image_destination.relative_to(output_dir)).replace("\\", "/")
            record = download_shot_asset(
                {
                    "shot_number": slot_number,
                    "visual_query": segment["visual_query"],
                    "on_screen_text": segment.get("on_screen_text", ""),
                },
                image_destination,
                logical_file=image_relative,
            )
            relative_file = image_relative
            if preferred_video:
                record.setdefault("errors", []).append("video-first fallback: no suitable Pexels video found; used image")

        record.update(
            {
                "beat_id": section.get("beat_id", ""),
                "beat_kind": section.get("beat_kind", ""),
                "section_key": section.get("section_key", ""),
                "evidence_ids": section.get("evidence_ids", []),
                "start_seconds": segment.get("start_seconds"),
                "end_seconds": segment.get("end_seconds"),
                "on_screen_text": segment.get("on_screen_text", ""),
                "reason": segment.get("reason", ""),
                "slot_priority": segment.get("slot_priority", "section_focus"),
                "preferred_asset_type": segment.get("preferred_asset_type", "image_or_video"),
                "motion_preference": segment.get("motion_preference", "normal"),
            }
        )
        manifest.append(record)
        selected_segments.append({**segment, "association": folder, "file": relative_file, "asset_type": record.get("asset_type", "image")})

    opening_assets = [
        item for item in manifest
        if float(item.get("start_seconds", 0) or 0) < OPENING_DENSE_MEDIA_SECONDS
    ]
    opening_videos = [item for item in opening_assets if item.get("asset_type") == "video"]
    if len(opening_assets) < min(OPENING_MIN_MEDIA_SLOTS, max_media_downloads):
        warnings.append(
            f"Cold open has only {len(opening_assets)} media assets in the first 20 seconds; target is {OPENING_MIN_MEDIA_SLOTS}"
        )
    if not opening_videos:
        warnings.append("Cold open contains no actual video assets; image fallbacks were used")

    if manifest:
        max_media_second = max(float(item.get("end_seconds", 0) or 0) for item in manifest)
        coverage_ratio = max_media_second / max(timeline_duration, 1)
        if coverage_ratio < 0.70:
            warnings.append(
                f"Review multimedia reaches only {coverage_ratio:.0%} of the essay duration; inspect coverage manually"
            )
    else:
        warnings.append("Review multimedia planner selected no external media")

    target_date = str(read_json(episode_dir / "run_state.json", {}).get("episode_date", episode_dir.name))
    write_json(
        output_dir / "plan.json",
        {
            "schema_version": 3,
            "review_only": True,
            "script_date": target_date,
            "timeline_duration_seconds": timeline_duration,
            "candidate_slot_count": len(timeline_slots),
            "max_media_downloads": max_media_downloads,
            "opening_dense_media_seconds": OPENING_DENSE_MEDIA_SECONDS,
            "opening_min_media_slots": OPENING_MIN_MEDIA_SLOTS,
            "opening_media_count": len(opening_assets),
            "opening_video_count": len(opening_videos),
            "validation_warnings": warnings,
            "segments": selected_segments,
            "agent_trace": trace,
        },
    )
    write_json(output_dir / "manifest.json", manifest)
    write_credits(manifest, output_dir)
    write_bundle_readme(output_dir, target_date=target_date, manifest=manifest)
    create_zip(output_dir, zip_path)
    return {
        "target_date": target_date,
        "asset_count": len(manifest),
        "opening_media_count": len(opening_assets),
        "opening_video_count": len(opening_videos),
        "zip_path": str(zip_path),
        "warnings": warnings,
        "manifest": manifest,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a beat-labelled multimedia review ZIP from any generated essay")
    parser.add_argument("--episode-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--zip-out", required=True)
    parser.add_argument("--max-media-downloads", type=int, default=12)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = asyncio.run(
        build_review_media(
            episode_dir=Path(args.episode_dir),
            output_dir=Path(args.output_dir),
            max_media_downloads=max(0, args.max_media_downloads),
            zip_path=Path(args.zip_out),
        )
    )
    print(json.dumps({k: v for k, v in result.items() if k != "manifest"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
