from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pipeline.core import PipelineConfig, timeline_duration_seconds
from pipeline.credits import write_credits
from pipeline.media import download_shot_asset, download_video_shot_asset
from pipeline.review_media import (
    OPENING_DENSE_MEDIA_SECONDS,
    association_label,
    build_review_candidate_slots,
    create_zip,
    media_filename,
    read_json,
    section_for_time,
    section_timeline,
    select_spread_media_budget,
    write_bundle_readme,
)
from pipeline.run import write_json

CONFIG = PipelineConfig.from_env()

_OPENING_QUERIES = (
    "cinematic close-up hands highlighting research notes documentary b-roll",
    "moving archival documents handwritten notes desk documentary footage",
    "investigative evidence wall notes connecting lines cinematic b-roll",
    "abstract flowing data traces light paths cinematic technology footage",
    "person carefully reviewing papers computer screen documentary footage",
    "close-up hands sorting research notes printed articles dynamic b-roll",
)

_KIND_QUERIES: dict[str, str] = {
    "historical_mirror": "historical archive manuscript writing knowledge documentary",
    "concrete_scene": "scientist researcher laboratory computer screen documentary",
    "first_reveal": "research evidence documents analysis close-up documentary",
    "complication": "complex decision evidence review computer documentary",
    "turn": "person reviewing evidence documents decision making documentary",
    "second_reveal": "research findings data evidence verification documentary",
    "human_peak": "human auditor reviewing checklist computer decision documentary",
    "evolved_thesis": "research evidence verification documents thoughtful analysis",
    "payoff": "thoughtful person reviewing notes evidence final question documentary",
}


def _selected_title_for_evidence(
    evidence_id: str,
    evidence_by_id: dict[str, dict[str, Any]],
    selected_items: list[dict[str, Any]],
) -> str:
    evidence = evidence_by_id.get(evidence_id, {})
    try:
        selected_index = int(evidence.get("selected_news_index", 0) or 0)
    except (TypeError, ValueError):
        return ""
    if not 1 <= selected_index <= len(selected_items):
        return ""
    item = selected_items[selected_index - 1]
    return str(item.get("title", "") or "").strip() if isinstance(item, dict) else ""


def _beat_query(
    beat: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
    selected_items: list[dict[str, Any]],
) -> str:
    evidence_titles = [
        _selected_title_for_evidence(str(evidence_id), evidence_by_id, selected_items)
        for evidence_id in beat.get("evidence_ids", []) or []
    ]
    evidence_titles = [title for title in evidence_titles if title]
    if evidence_titles:
        # Keep the concrete entity/name from the source, while nudging providers toward documentary visuals.
        return f"{evidence_titles[0]} research documentary evidence"

    kind = str(beat.get("kind", "") or "").strip().lower()
    if kind in _KIND_QUERIES:
        return _KIND_QUERIES[kind]
    purpose = str(beat.get("purpose", "") or "").strip()
    return f"{purpose} documentary research evidence" if purpose else "research evidence documentary"


def build_deterministic_plan(
    *,
    episode_plan: dict[str, Any],
    selected_news: dict[str, Any],
    candidate_slots: list[dict[str, Any]],
    max_media_downloads: int,
) -> list[dict[str, Any]]:
    """Build a no-LLM visual plan from narrative beats and evidence.

    Policy:
    - every candidate slot in the first 20 seconds is multimedia/video-first;
    - after 20 seconds, use one representative visual per narrative beat;
    - always keep a synthesis visual payoff;
    - if the budget is smaller than the plan, preserve opening + synthesis and spread the rest.
    """
    evidence_by_id = {
        str(item.get("evidence_id", "")): item
        for item in episode_plan.get("evidence", [])
        if isinstance(item, dict) and str(item.get("evidence_id", "")).strip()
    }
    selected_items = [
        item for item in selected_news.get("items", []) if isinstance(item, dict)
    ] if isinstance(selected_news, dict) else []
    beat_by_id = {
        str(item.get("beat_id", "")): item
        for item in episode_plan.get("beats", [])
        if isinstance(item, dict) and str(item.get("beat_id", "")).strip()
    }

    used_sections: set[str] = set()
    plan: list[dict[str, Any]] = []
    opening_index = 0
    for slot in candidate_slots:
        start = float(slot.get("start_seconds", 0) or 0)
        section_key = str(slot.get("section_key", "") or "")
        if start < OPENING_DENSE_MEDIA_SECONDS:
            query = _OPENING_QUERIES[opening_index % len(_OPENING_QUERIES)]
            opening_index += 1
            plan.append({
                **slot,
                "mode": "media",
                "visual_query": query,
                "on_screen_text": "",
                "reason": "Deterministic dense cold open: motion-first visual",
                "slot_priority": "opening_dense_media",
                "preferred_asset_type": "video",
                "motion_preference": "high",
            })
            continue

        if section_key == "synthesis":
            plan.append({
                **slot,
                "mode": "media",
                "visual_query": "thoughtful final question person reflecting over notes and evidence documentary",
                "on_screen_text": "¿Qué cuenta como conocimiento verificable?",
                "reason": "Deterministic synthesis visual payoff",
                "slot_priority": "synthesis_payoff",
                "preferred_asset_type": "image_or_video",
                "motion_preference": "normal",
            })
            used_sections.add(section_key)
            continue

        if section_key in used_sections:
            plan.append({
                **slot,
                "mode": "presenter",
                "visual_query": "",
                "on_screen_text": "",
                "reason": "One explanatory asset per beat in deterministic review mode",
            })
            continue

        beat_id = str(slot.get("beat_id", "") or "")
        beat = beat_by_id.get(beat_id, {})
        plan.append({
            **slot,
            "mode": "media",
            "visual_query": _beat_query(beat, evidence_by_id, selected_items),
            "on_screen_text": str(beat.get("purpose", "") or "")[:80],
            "reason": "Deterministic beat/evidence visual",
            "slot_priority": "section_focus",
            "preferred_asset_type": "image_or_video",
            "motion_preference": "normal",
        })
        used_sections.add(section_key)

    return select_spread_media_budget(plan, max_media_downloads=max(0, max_media_downloads))


def build_offline_review_media(
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
    selected_news = read_json(episode_dir / "selected_news.json", {})
    if not episode_plan.get("beats"):
        raise ValueError("episode_plan.json has no idea-led beats")
    if not script_sections.get("sections"):
        raise ValueError("script_sections.json is required for beat/media association")

    output_dir.mkdir(parents=True, exist_ok=True)
    timeline_duration = timeline_duration_seconds(script, CONFIG)
    section_ranges = section_timeline(script_sections, CONFIG.words_per_second)
    candidate_slots = build_review_candidate_slots(section_ranges)
    plan = build_deterministic_plan(
        episode_plan=episode_plan,
        selected_news=selected_news,
        candidate_slots=candidate_slots,
        max_media_downloads=max_media_downloads,
    )

    manifest: list[dict[str, Any]] = []
    selected_segments: list[dict[str, Any]] = []
    for segment in plan:
        if segment.get("mode") != "media":
            continue
        slot_number = int(segment.get("slot_number", 0) or 0)
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
                record.setdefault("errors", []).append(
                    "video-first fallback: no suitable Pexels video found; used image"
                )

        record.update({
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
        })
        manifest.append(record)
        selected_segments.append({
            **segment,
            "association": folder,
            "file": relative_file,
            "asset_type": record.get("asset_type", "image"),
        })

    opening_assets = [
        item for item in manifest
        if float(item.get("start_seconds", 0) or 0) < OPENING_DENSE_MEDIA_SECONDS
    ]
    opening_videos = [item for item in opening_assets if item.get("asset_type") == "video"]
    max_media_second = max(
        (float(item.get("end_seconds", 0) or 0) for item in manifest), default=0.0
    )
    coverage_ratio = max_media_second / max(timeline_duration, 1)
    warnings: list[str] = [
        "LLM multimedia planner unavailable; deterministic beat/evidence planner used"
    ]
    if coverage_ratio < 0.85:
        warnings.append(
            f"Deterministic review multimedia reaches only {coverage_ratio:.0%} of essay duration"
        )

    target_date = str(
        read_json(episode_dir / "run_state.json", {}).get("episode_date", episode_dir.name)
    )
    write_json(output_dir / "plan.json", {
        "schema_version": 4,
        "review_only": True,
        "planner_mode": "deterministic_offline",
        "script_date": target_date,
        "timeline_duration_seconds": timeline_duration,
        "candidate_slot_count": len(candidate_slots),
        "max_media_downloads": max_media_downloads,
        "opening_dense_media_seconds": OPENING_DENSE_MEDIA_SECONDS,
        "opening_media_count": len(opening_assets),
        "opening_video_count": len(opening_videos),
        "coverage_ratio": round(coverage_ratio, 4),
        "validation_warnings": warnings,
        "segments": selected_segments,
        "agent_trace": [],
    })
    write_json(output_dir / "manifest.json", manifest)
    write_credits(manifest, output_dir)
    write_bundle_readme(output_dir, target_date=target_date, manifest=manifest)
    create_zip(output_dir, zip_path)
    return {
        "target_date": target_date,
        "asset_count": len(manifest),
        "opening_media_count": len(opening_assets),
        "opening_video_count": len(opening_videos),
        "coverage_ratio": round(coverage_ratio, 4),
        "zip_path": str(zip_path),
        "warnings": warnings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build beat/evidence-labelled review multimedia without an LLM"
    )
    parser.add_argument("--episode-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--zip-out", required=True)
    parser.add_argument("--max-media-downloads", type=int, default=18)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_offline_review_media(
        episode_dir=Path(args.episode_dir),
        output_dir=Path(args.output_dir),
        max_media_downloads=max(0, args.max_media_downloads),
        zip_path=Path(args.zip_out),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
