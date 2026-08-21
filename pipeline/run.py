from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agent import multimedia_editor_agent, root_agent
from pipeline.media import download_shot_asset

APP_NAME = "ai_news_daily_video"
USER_ID = "github_actions"
WORDS_PER_SECOND = float(os.getenv("WORDS_PER_SECOND", "2.5"))
FIRST_15_SLOT_SECONDS = 3
NORMAL_SLOT_SECONDS = 4
MAX_MEDIA_DOWNLOADS = int(os.getenv("MAX_MEDIA_DOWNLOADS", "12"))
DOWNLOAD_MULTIMEDIA = os.getenv("DOWNLOAD_MULTIMEDIA", "true").strip().lower() not in {"0", "false", "no"}
SELECTION_HISTORY_DAYS = int(os.getenv("SELECTION_HISTORY_DAYS", "30"))
QUALITY_THRESHOLD = float(os.getenv("SCRIPT_QUALITY_THRESHOLD", "8.7"))
JUDGE_THRESHOLD = float(os.getenv("JUDGE_THRESHOLD", "8.5"))


def parse_target_date(value: str | None) -> date:
    if value:
        return datetime.strptime(value, "%Y-%m-%d").date()
    return date.today()


def expected_news_dates(target_date: date) -> list[date]:
    """Return the editorial input window for a Tuesday or Friday script."""
    if target_date.weekday() == 1:  # Tuesday -> Friday, Saturday, Sunday, Monday
        offsets = (4, 3, 2, 1)
    elif target_date.weekday() == 4:  # Friday -> Tuesday, Wednesday, Thursday
        offsets = (3, 2, 1)
    else:
        raise ValueError(
            f"Script generation only runs on Tuesday or Friday; got {target_date.isoformat()}"
        )
    return [target_date - timedelta(days=offset) for offset in offsets]


def collect_available_news(news_dir: Path, target_date: date) -> tuple[str, list[Path], list[date]]:
    expected = expected_news_dates(target_date)
    available: list[Path] = []
    missing: list[date] = []
    sections: list[str] = []

    for news_date in expected:
        path = news_dir / f"{news_date.isoformat()}.txt"
        if not path.exists():
            missing.append(news_date)
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            missing.append(news_date)
            continue
        available.append(path)
        sections.append(
            f"\n===== SOURCE NEWS FILE: {path.name} =====\n{text}\n===== END SOURCE: {path.name} ====="
        )

    return "\n".join(sections).strip(), available, missing


def load_selection_history(scripts_dir: Path, target_date: date, lookback_days: int) -> str:
    cutoff = target_date - timedelta(days=max(1, lookback_days))
    items: list[dict[str, Any]] = []

    if not scripts_dir.exists():
        return "[]"

    for path in sorted(scripts_dir.glob("*/selected_news.json"), reverse=True):
        try:
            episode_date = datetime.strptime(path.parent.name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if episode_date >= target_date or episode_date < cutoff:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for item in payload.get("items", []):
            if isinstance(item, dict):
                items.append(
                    {
                        "title": item.get("title", ""),
                        "date": item.get("date", ""),
                        "source": item.get("source", ""),
                        "url": item.get("url", ""),
                        "summary": item.get("summary", ""),
                    }
                )

    return json.dumps(items[-40:], ensure_ascii=False)


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
    raw = max(60.0, min(100.0, words / WORDS_PER_SECOND))
    return 15 + math.ceil(max(0.0, raw - 15) / NORMAL_SLOT_SECONDS) * NORMAL_SLOT_SECONDS


def build_timeline_slots(duration_seconds: int) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    cursor = 0
    slot_number = 1

    while cursor < duration_seconds:
        step = FIRST_15_SLOT_SECONDS if cursor < 15 else NORMAL_SLOT_SECONDS
        end = min(duration_seconds, cursor + step)
        slots.append(
            {
                "slot_number": slot_number,
                "start_seconds": cursor,
                "end_seconds": end,
                "duration_seconds": end - cursor,
            }
        )
        cursor = end
        slot_number += 1

    return slots


def normalize_multimedia_plan(
    raw_plan: dict[str, Any],
    timeline_slots: list[dict[str, Any]],
    max_media_downloads: int,
) -> list[dict[str, Any]]:
    raw_segments = raw_plan.get("segments") or []
    by_number = {
        int(segment.get("slot_number", -1)): segment
        for segment in raw_segments
        if isinstance(segment, dict)
    }
    normalized: list[dict[str, Any]] = []
    media_count = 0

    for slot in timeline_slots:
        segment = by_number.get(slot["slot_number"], {})
        requested_mode = str(segment.get("mode", "presenter")).lower()
        query = str(segment.get("visual_query", "")).strip()
        mode = "media" if requested_mode == "media" and query else "presenter"

        if mode == "media":
            if media_count >= max_media_downloads:
                mode = "presenter"
                query = ""
            else:
                media_count += 1
        else:
            query = ""

        normalized.append(
            {
                **slot,
                "mode": mode,
                "visual_query": query,
                "on_screen_text": str(segment.get("on_screen_text", "")).strip()[:80],
                "reason": str(segment.get("reason", "")).strip(),
            }
        )

    return normalized


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def all_judges_approved(script_state: dict[str, Any]) -> bool:
    editorial = script_state.get("review") or {}
    seo = script_state.get("seo_review") or {}
    attention = script_state.get("attention_review") or {}
    return bool(
        editorial.get("approved")
        and float(editorial.get("score", 0) or 0) >= QUALITY_THRESHOLD
        and str(editorial.get("factuality_risk", "")).lower() == "low"
        and seo.get("approved")
        and float(seo.get("score", 0) or 0) >= JUDGE_THRESHOLD
        and attention.get("approved")
        and float(attention.get("score", 0) or 0) >= JUDGE_THRESHOLD
    )


async def build(
    target_date: date,
    news_dir: Path,
    scripts_root: Path,
    multimedia_root: Path,
    max_media_downloads: int,
    download_multimedia: bool,
) -> Path | None:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY before running the pipeline")

    news_text, available_files, missing_dates = collect_available_news(news_dir, target_date)
    expected_dates = expected_news_dates(target_date)

    print("Target script date:", target_date.isoformat())
    print("Expected news dates:", ", ".join(d.isoformat() for d in expected_dates))
    print("Available news files:", ", ".join(p.name for p in available_files) or "none")
    if missing_dates:
        print(
            "WARNING: missing/empty news dates (continuing with what is available):",
            ", ".join(d.isoformat() for d in missing_dates),
        )

    if not news_text:
        print("No usable news found in the editorial window. Nothing to build; exiting successfully.")
        return None

    episode_scripts_dir = scripts_root / target_date.isoformat()
    episode_media_dir = multimedia_root / target_date.isoformat()
    episode_scripts_dir.mkdir(parents=True, exist_ok=True)

    previous_selected_news = load_selection_history(
        scripts_root, target_date, SELECTION_HISTORY_DAYS
    )

    script_state = await run_agent(
        root_agent,
        {
            "news_text": news_text,
            "previous_selected_news": previous_selected_news,
        },
        "Select the unique high-value stories, create the Spanish AI-news script, and iterate until every judge approves it.",
    )

    final_script = str(script_state.get("draft_script", "")).strip()
    if not final_script:
        raise RuntimeError("ADK did not produce draft_script")

    (episode_scripts_dir / "script.txt").write_text(final_script + "\n", encoding="utf-8")
    write_json(episode_scripts_dir / "selected_news.json", script_state.get("selected_news", {}))
    approved = all_judges_approved(script_state)
    write_json(
        episode_scripts_dir / "reviews.json",
        {
            "approved_for_multimedia": approved,
            "editorial": script_state.get("review", {}),
            "seo_master": script_state.get("seo_review", {}),
            "youtube_attention_master": script_state.get("attention_review", {}),
            "source_files": [path.name for path in available_files],
            "missing_dates": [d.isoformat() for d in missing_dates],
        },
    )

    if not approved:
        print(
            "The iteration cap was reached without unanimous judge approval. "
            "Script/reviews were saved, but multimedia planning and downloading are skipped."
        )
        return episode_scripts_dir

    duration_seconds = estimate_duration_seconds(final_script)
    timeline_slots = build_timeline_slots(duration_seconds)
    editor_state = await run_agent(
        multimedia_editor_agent,
        {
            "final_script": final_script,
            "timeline_slots": json.dumps(timeline_slots, ensure_ascii=False),
            "max_media_downloads": max(0, max_media_downloads),
        },
        "Create the final multimedia/presenter edit plan using the canonical timeline slots.",
    )
    multimedia_plan = normalize_multimedia_plan(
        editor_state.get("multimedia_plan", {}),
        timeline_slots,
        max(0, max_media_downloads),
    )

    write_json(
        episode_media_dir / "plan.json",
        {
            "script_date": target_date.isoformat(),
            "duration_seconds": duration_seconds,
            "first_15_seconds_slot_size": FIRST_15_SLOT_SECONDS,
            "normal_slot_size": NORMAL_SLOT_SECONDS,
            "max_media_downloads": max(0, max_media_downloads),
            "segments": multimedia_plan,
        },
    )

    manifest: list[dict[str, Any]] = []
    if download_multimedia:
        assets_dir = episode_media_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        for segment in multimedia_plan:
            if segment["mode"] != "media":
                continue
            destination = assets_dir / f"slot_{segment['slot_number']:03d}.jpg"
            manifest.append(
                download_shot_asset(
                    {
                        "shot_number": segment["slot_number"],
                        "visual_query": segment["visual_query"],
                        "on_screen_text": segment["on_screen_text"],
                    },
                    destination,
                )
            )
    else:
        print("DOWNLOAD_MULTIMEDIA=false: edit plan created, external media download skipped.")

    write_json(episode_media_dir / "manifest.json", manifest)
    print(f"Approved script created at {episode_scripts_dir / 'script.txt'}")
    print(f"Multimedia plan created at {episode_media_dir / 'plan.json'}")
    print(f"Downloaded multimedia assets: {len(manifest)}")
    return episode_scripts_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Tuesday/Friday AI-news video kit")
    parser.add_argument("--target-date", default=None, help="YYYY-MM-DD; must be Tuesday or Friday")
    parser.add_argument("--news-dir", default="news")
    parser.add_argument("--scripts-dir", default="scripts")
    parser.add_argument("--multimedia-dir", default="multimedia")
    parser.add_argument("--max-media-downloads", type=int, default=MAX_MEDIA_DOWNLOADS)
    parser.add_argument(
        "--no-download-multimedia",
        action="store_true",
        help="Create the edit plan but do not download external multimedia.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target_date = parse_target_date(args.target_date)
    asyncio.run(
        build(
            target_date=target_date,
            news_dir=Path(args.news_dir),
            scripts_root=Path(args.scripts_dir),
            multimedia_root=Path(args.multimedia_dir),
            max_media_downloads=args.max_media_downloads,
            download_multimedia=DOWNLOAD_MULTIMEDIA and not args.no_download_multimedia,
        )
    )


if __name__ == "__main__":
    main()
