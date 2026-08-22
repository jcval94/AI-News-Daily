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
from pipeline.media import download_shot_asset
from pipeline.run import normalize_multimedia_plan, run_agent, write_json

CONFIG = PipelineConfig.from_env()


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
    """Offer a small, evenly distributed set of visual slots across the essay.

    The production timeline may contain hundreds of slots and encourages cheap models to focus on
    the earliest entries. Review media instead offers one or two representative windows per idea-led
    section so the visual planner sees the full dramaturgical arc.
    """
    slots: list[dict[str, Any]] = []
    slot_number = 1
    for section in section_ranges:
        start = float(section.get("start_seconds", 0) or 0)
        end = float(section.get("end_seconds", start) or start)
        duration = max(0.0, end - start)
        key = str(section.get("section_key", "") or "")
        if duration <= 0:
            continue
        if key in {"opening", "synthesis"}:
            fractions = (0.55,)
        elif duration >= 28:
            fractions = (0.30, 0.72)
        else:
            fractions = (0.52,)
        for fraction in fractions:
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


def media_filename(segment: dict[str, Any]) -> str:
    slot = int(segment.get("slot_number", 0) or 0)
    start = int(round(float(segment.get("start_seconds", 0) or 0)))
    end = int(round(float(segment.get("end_seconds", 0) or 0)))
    label = slug(segment.get("on_screen_text") or segment.get("visual_query"), fallback="visual", limit=48)
    return f"S{slot:03d}__{start:04d}-{end:04d}s__{label}.jpg"


def write_bundle_readme(output_dir: Path, *, target_date: str, manifest: list[dict[str, Any]]) -> None:
    lines = [
        f"# Review multimedia — {target_date}",
        "",
        "This bundle is for editorial review only; it does not imply episode approval.",
        "",
        "Folders are associated to narrative beats, not news order:",
        "`B##_beat-id__E_evidence-id/...`.",
        "",
        "Each filename contains the candidate slot and approximate seconds:",
        "`S###__start-end__description.jpg`.",
        "",
        f"Assets: {len(manifest)}",
        "",
    ]
    for item in manifest:
        lines.append(
            f"- `{item.get('file', '')}` — {item.get('provider', '')}; "
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
        },
        (
            "Plan review multimedia across the FULL essay, not only the opening. Inspect every idea-led beat. "
            "Use at most two assets in any single beat; preserve budget for the complication, narrative turn, "
            "human stakes and final synthesis when a visual materially helps. Prefer explanatory/documentary "
            "queries over generic metaphors or stock-photo symbolism."
        ),
        step="review_plan_multimedia",
        trace=trace,
    )
    raw_plan = MultimediaPlan.model_validate(editor_state.get("multimedia_plan", {})).model_dump()
    normalized, warnings = normalize_multimedia_plan(raw_plan, timeline_slots, max(0, max_media_downloads))

    selected_segments: list[dict[str, Any]] = []
    manifest: list[dict[str, Any]] = []
    for segment in normalized:
        if segment.get("mode") != "media":
            continue
        section = section_for_time(
            section_ranges,
            float(segment.get("start_seconds", 0) or 0),
            float(segment.get("end_seconds", 0) or 0),
        )
        folder = association_label(section)
        filename = media_filename(segment)
        destination = output_dir / folder / filename
        relative_file = str(destination.relative_to(output_dir)).replace("\\", "/")
        record = download_shot_asset(
            {
                "shot_number": int(segment["slot_number"]),
                "visual_query": segment["visual_query"],
                "on_screen_text": segment.get("on_screen_text", ""),
            },
            destination,
            logical_file=relative_file,
        )
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
            }
        )
        manifest.append(record)
        selected_segments.append({**segment, "association": folder, "file": relative_file})

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
            "schema_version": 2,
            "review_only": True,
            "script_date": target_date,
            "timeline_duration_seconds": timeline_duration,
            "candidate_slot_count": len(timeline_slots),
            "max_media_downloads": max_media_downloads,
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
