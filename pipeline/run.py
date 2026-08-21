from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import shutil
import subprocess
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agent import multimedia_editor_agent, root_agent
from pipeline.media import download_shot_asset, make_fallback_card

APP_NAME = "ai_news_daily_video"
USER_ID = "github_actions"
WORDS_PER_SECOND = float(os.getenv("WORDS_PER_SECOND", "2.5"))
NEWS_TIMEZONE = os.getenv("NEWS_TIMEZONE", "America/Mexico_City")
HOOK_SECONDS = int(os.getenv("HOOK_SECONDS", "15"))
HOOK_SLOT_SECONDS = int(os.getenv("HOOK_SLOT_SECONDS", "3"))
MEDIA_SLOT_SECONDS = int(os.getenv("MEDIA_SLOT_SECONDS", "4"))
MAX_MEDIA_DOWNLOADS = int(os.getenv("MAX_MEDIA_DOWNLOADS", "12"))


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(_jsonable(value), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def resolve_run_date(value: str | None) -> date:
    if value:
        return date.fromisoformat(value)
    return datetime.now(ZoneInfo(NEWS_TIMEZONE)).date()


def scheduled_news_dates(run_date: date) -> list[date]:
    """Tuesday uses Fri-Mon; Friday uses Tue-Thu. Other days intentionally do nothing."""
    if run_date.weekday() == 1:  # Tuesday
        offsets = [4, 3, 2, 1]  # Friday, Saturday, Sunday, Monday
    elif run_date.weekday() == 4:  # Friday
        offsets = [3, 2, 1]  # Tuesday, Wednesday, Thursday
    else:
        return []
    return [run_date - timedelta(days=offset) for offset in offsets]


def scheduled_news_files(news_dir: Path, run_date: date) -> list[Path]:
    """Return only files that actually exist; missing daily digests never break the run."""
    files: list[Path] = []
    for day in scheduled_news_dates(run_date):
        candidate = news_dir / f"{day.isoformat()}.txt"
        if candidate.is_file() and candidate.stat().st_size > 0:
            files.append(candidate)
        else:
            print(f"Skipping unavailable news file: {candidate}")
    return files


def latest_news_file(news_dir: Path) -> Path | None:
    files = sorted(path for path in news_dir.glob("*.txt") if path.stat().st_size > 0)
    return files[-1] if files else None


def combine_news_files(news_files: list[Path]) -> str:
    chunks: list[str] = []
    for path in news_files:
        text = path.read_text(encoding="utf-8").strip()
        if text:
            chunks.append(f"===== NEWS FILE: {path.name} =====\n{text}")
    return "\n\n".join(chunks)


async def run_agent(agent, initial_state: dict[str, Any], prompt: str) -> dict[str, Any]:
    session_service = InMemorySessionService()
    session_id = uuid.uuid4().hex
    await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=session_id,
        state=initial_state,
    )
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)
    message = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    async for _ in runner.run_async(
        user_id=USER_ID,
        session_id=session_id,
        new_message=message,
    ):
        pass
    session = await session_service.get_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=session_id,
    )
    if session is None:
        raise RuntimeError("ADK session disappeared unexpectedly")
    return dict(session.state)


def estimate_duration_seconds(script: str) -> int:
    words = max(1, len(script.split()))
    raw = max(60.0, min(99.0, words / WORDS_PER_SECOND))
    if raw <= HOOK_SECONDS:
        return HOOK_SECONDS
    post_hook = math.ceil((raw - HOOK_SECONDS) / MEDIA_SLOT_SECONDS) * MEDIA_SLOT_SECONDS
    return HOOK_SECONDS + post_hook


def timeline_slots(duration_seconds: int) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    start = 0
    slot_number = 1

    hook_end = min(HOOK_SECONDS, duration_seconds)
    while start < hook_end:
        end = min(start + HOOK_SLOT_SECONDS, hook_end)
        slots.append(
            {
                "slot_number": slot_number,
                "start_seconds": start,
                "end_seconds": end,
                "duration_seconds": end - start,
            }
        )
        slot_number += 1
        start = end

    while start < duration_seconds:
        end = min(start + MEDIA_SLOT_SECONDS, duration_seconds)
        slots.append(
            {
                "slot_number": slot_number,
                "start_seconds": start,
                "end_seconds": end,
                "duration_seconds": end - start,
            }
        )
        slot_number += 1
        start = end

    return slots


def _approved(value: Any, threshold: float, require_low_risk: bool = False) -> bool:
    data = _jsonable(value) or {}
    if not isinstance(data, dict):
        return False
    approved = bool(data.get("approved")) and float(data.get("score", 0)) >= threshold
    if require_low_risk:
        approved = approved and str(data.get("factuality_risk", "")).lower() == "low"
    return approved


def all_judges_approved(state: dict[str, Any]) -> bool:
    quality_threshold = float(os.getenv("SCRIPT_QUALITY_THRESHOLD", "8.7"))
    judge_threshold = float(os.getenv("JUDGE_THRESHOLD", "8.5"))
    return (
        _approved(state.get("review"), quality_threshold, require_low_risk=True)
        and _approved(state.get("seo_review"), judge_threshold)
        and _approved(state.get("attention_review"), judge_threshold)
    )


def normalize_multimedia_plan(
    raw: Any,
    canonical_slots: list[dict[str, Any]],
    max_media_downloads: int,
) -> list[dict[str, Any]]:
    data = _jsonable(raw) or {}
    proposed = data.get("segments", []) if isinstance(data, dict) else []
    by_number = {
        int(item.get("slot_number")): item
        for item in proposed
        if isinstance(item, dict) and str(item.get("slot_number", "")).isdigit()
    }

    normalized: list[dict[str, Any]] = []
    media_count = 0
    for slot in canonical_slots:
        proposal = by_number.get(slot["slot_number"], {})
        mode = proposal.get("mode", "presenter")
        visual_query = str(proposal.get("visual_query", "")).strip()

        if mode == "media" and visual_query and media_count < max_media_downloads:
            media_count += 1
        else:
            mode = "presenter"
            visual_query = ""

        normalized.append(
            {
                **slot,
                "mode": mode,
                "visual_query": visual_query,
                "on_screen_text": str(proposal.get("on_screen_text", "")).strip()[:80],
                "reason": str(proposal.get("reason", "")).strip(),
            }
        )
    return normalized


def render_preview(frames: list[tuple[Path, float]], destination: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not frames:
        return False

    concat_file = destination.parent / "frames.ffconcat"
    lines = ["ffconcat version 1.0"]
    for image, duration in frames:
        lines.append(f"file '{image.resolve().as_posix()}'")
        lines.append(f"duration {duration}")
    lines.append(f"file '{frames[-1][0].resolve().as_posix()}'")
    concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    command = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-vf",
        "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
        "-r",
        "30",
        "-pix_fmt",
        "yuv420p",
        str(destination),
    ]
    subprocess.run(command, check=True)
    return True


async def build(news_files: list[Path], output_root: Path, run_date: date) -> Path:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY before running the pipeline")

    output_dir = output_root / run_date.isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)

    news_text = combine_news_files(news_files)
    if not news_text:
        write_json(
            output_dir / "status.json",
            {
                "status": "skipped_no_news",
                "run_date": run_date.isoformat(),
                "expected_dates": [day.isoformat() for day in scheduled_news_dates(run_date)],
                "available_files": [],
            },
        )
        print("No usable news files were available. Run completed without error.")
        return output_dir

    script_state = await run_agent(
        root_agent,
        {"news_text": news_text},
        "Select the strongest unique stories and create the final youth-oriented AI-news script. Refine until all judges approve or the iteration cap is reached.",
    )

    final_script = str(script_state.get("draft_script", "")).strip()
    if not final_script:
        raise RuntimeError("ADK did not produce draft_script")

    (output_dir / "script.txt").write_text(final_script + "\n", encoding="utf-8")
    write_json(output_dir / "selection.json", script_state.get("selected_news", {}))
    write_json(output_dir / "review.json", script_state.get("review", {}))
    write_json(output_dir / "seo_review.json", script_state.get("seo_review", {}))
    write_json(output_dir / "attention_review.json", script_state.get("attention_review", {}))

    if not all_judges_approved(script_state):
        write_json(
            output_dir / "status.json",
            {
                "status": "script_not_approved",
                "run_date": run_date.isoformat(),
                "source_files": [str(path) for path in news_files],
                "message": "Script was saved, but multimedia was intentionally not downloaded because all judges did not approve it.",
            },
        )
        print("Script did not receive all required approvals. Multimedia download skipped by design.")
        return output_dir

    duration_seconds = estimate_duration_seconds(final_script)
    canonical_slots = timeline_slots(duration_seconds)
    max_media_downloads = max(0, MAX_MEDIA_DOWNLOADS)

    editor_state = await run_agent(
        multimedia_editor_agent,
        {
            "final_script": final_script,
            "timeline_slots": canonical_slots,
            "max_media_downloads": max_media_downloads,
        },
        "Create the final presenter/media edit plan. Downloadable media must be used only where it materially improves the video.",
    )
    edit_plan = normalize_multimedia_plan(
        editor_state.get("multimedia_plan", {}),
        canonical_slots,
        max_media_downloads,
    )
    write_json(
        output_dir / "editor_plan.json",
        {
            "duration_seconds": duration_seconds,
            "first_15_seconds_slot_seconds": HOOK_SLOT_SECONDS,
            "post_hook_slot_seconds": MEDIA_SLOT_SECONDS,
            "max_media_downloads": max_media_downloads,
            "segments": edit_plan,
        },
    )

    media_dir = output_dir / "media"
    preview_dir = output_dir / "preview_frames"
    media_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, Any]] = []
    preview_frames: list[tuple[Path, float]] = []
    downloaded_media = 0

    for segment in edit_plan:
        duration = float(segment["duration_seconds"])
        slot_number = int(segment["slot_number"])

        if segment["mode"] == "media":
            destination = media_dir / f"slot_{slot_number:03d}.jpg"
            record = download_shot_asset(
                {
                    "shot_number": slot_number,
                    "visual_query": segment["visual_query"],
                    "on_screen_text": segment["on_screen_text"],
                },
                destination,
            )
            downloaded_media += 1
            record.update(
                {
                    "mode": "media",
                    "start_seconds": segment["start_seconds"],
                    "end_seconds": segment["end_seconds"],
                    "duration_seconds": duration,
                    "downloaded": True,
                }
            )
            manifest.append(record)
        else:
            destination = preview_dir / f"slot_{slot_number:03d}_presenter.jpg"
            label = segment["on_screen_text"] or "PERSONA EN CÁMARA"
            make_fallback_card(f"PERSONA EN CÁMARA — {label}", destination)
            manifest.append(
                {
                    "slot_number": slot_number,
                    "mode": "presenter",
                    "start_seconds": segment["start_seconds"],
                    "end_seconds": segment["end_seconds"],
                    "duration_seconds": duration,
                    "downloaded": False,
                    "file": str(destination),
                }
            )

        preview_frames.append((destination, duration))

    write_json(output_dir / "media_manifest.json", manifest)
    render_preview(preview_frames, output_dir / "preview.mp4")
    write_json(
        output_dir / "status.json",
        {
            "status": "complete",
            "run_date": run_date.isoformat(),
            "source_files": [str(path) for path in news_files],
            "downloaded_media_count": downloaded_media,
            "max_media_downloads": max_media_downloads,
        },
    )
    return output_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an AI-news video kit")
    parser.add_argument(
        "--news",
        default="scheduled",
        help="'scheduled' for Tue/Fri windows, 'latest', or a specific .txt path",
    )
    parser.add_argument("--news-dir", default="news")
    parser.add_argument("--run-date", default=None, help="Optional YYYY-MM-DD override for testing")
    parser.add_argument("--out", default="outputs")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_date = resolve_run_date(args.run_date)
    news_dir = Path(args.news_dir)

    if args.news == "scheduled":
        news_files = scheduled_news_files(news_dir, run_date)
    elif args.news == "latest":
        latest = latest_news_file(news_dir)
        news_files = [latest] if latest else []
    else:
        specific = Path(args.news)
        news_files = [specific] if specific.is_file() and specific.stat().st_size > 0 else []

    output_dir = asyncio.run(build(news_files, Path(args.out), run_date))
    print(f"Video kit process completed at {output_dir}")


if __name__ == "__main__":
    main()
