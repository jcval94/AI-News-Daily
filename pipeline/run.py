from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agent import root_agent, storyboard_agent
from pipeline.media import download_shot_asset

APP_NAME = "ai_news_daily_video"
USER_ID = "github_actions"
WORDS_PER_SECOND = float(os.getenv("WORDS_PER_SECOND", "2.5"))
SHOT_SECONDS = 4


def latest_news_file(news_dir: Path) -> Path:
    files = sorted(news_dir.glob("*.txt"))
    if not files:
        raise FileNotFoundError(f"No .txt news files found under {news_dir}")
    return files[-1]


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
    raw = words / WORDS_PER_SECOND
    rounded = math.ceil(raw / SHOT_SECONDS) * SHOT_SECONDS
    return max(60, min(100, rounded))


def normalize_storyboard(raw: dict[str, Any], shot_count: int) -> list[dict[str, Any]]:
    shots = list(raw.get("shots") or [])
    if len(shots) > shot_count:
        shots = shots[:shot_count]
    while len(shots) < shot_count:
        number = len(shots) + 1
        shots.append(
            {
                "shot_number": number,
                "visual_query": "artificial intelligence technology abstract data center",
                "on_screen_text": "IA: lo importante de hoy",
                "visual_type": "fallback",
            }
        )
    normalized = []
    for index, shot in enumerate(shots, start=1):
        normalized.append(
            {
                **shot,
                "shot_number": index,
                "start_seconds": (index - 1) * SHOT_SECONDS,
                "end_seconds": index * SHOT_SECONDS,
                "duration_seconds": SHOT_SECONDS,
            }
        )
    return normalized


def render_preview(media_files: list[Path], destination: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not media_files:
        return False
    concat_file = destination.parent / "frames.ffconcat"
    lines = ["ffconcat version 1.0"]
    for image in media_files:
        lines.append(f"file '{image.resolve().as_posix()}'")
        lines.append(f"duration {SHOT_SECONDS}")
    lines.append(f"file '{media_files[-1].resolve().as_posix()}'")
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


async def build(news_file: Path, output_root: Path) -> Path:
    if not os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError("Set GEMINI_API_KEY (or GOOGLE_API_KEY) before running the pipeline")

    news_text = news_file.read_text(encoding="utf-8").strip()
    if not news_text:
        raise ValueError(f"News file is empty: {news_file}")

    date_key = news_file.stem
    output_dir = output_root / date_key
    media_dir = output_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    script_state = await run_agent(
        root_agent,
        {"news_text": news_text},
        "Create today's youth-oriented AI-news video script and iterate until it passes quality review.",
    )
    final_script = str(script_state.get("draft_script", "")).strip()
    if not final_script:
        raise RuntimeError("ADK did not produce draft_script")

    duration_seconds = estimate_duration_seconds(final_script)
    shot_count = duration_seconds // SHOT_SECONDS
    storyboard_state = await run_agent(
        storyboard_agent,
        {
            "final_script": final_script,
            "shot_count": shot_count,
        },
        f"Create exactly {shot_count} visual shots, one per 4 seconds.",
    )
    storyboard = normalize_storyboard(storyboard_state.get("storyboard", {}), shot_count)

    (output_dir / "script.txt").write_text(final_script + "\n", encoding="utf-8")
    (output_dir / "review.json").write_text(
        json.dumps(script_state.get("review", {}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "storyboard.json").write_text(
        json.dumps(
            {
                "source_news": str(news_file),
                "duration_seconds": duration_seconds,
                "shot_seconds": SHOT_SECONDS,
                "shots": storyboard,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    manifest = []
    media_files: list[Path] = []
    for shot in storyboard:
        destination = media_dir / f"shot_{shot['shot_number']:03d}.jpg"
        manifest.append(download_shot_asset(shot, destination))
        media_files.append(destination)

    (output_dir / "media_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    render_preview(media_files, output_dir / "preview.mp4")
    return output_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a daily AI-news video kit")
    parser.add_argument("--news", default="latest", help="Path to news .txt or 'latest'")
    parser.add_argument("--news-dir", default="news")
    parser.add_argument("--out", default="outputs")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    news_file = latest_news_file(Path(args.news_dir)) if args.news == "latest" else Path(args.news)
    output_dir = asyncio.run(build(news_file, Path(args.out)))
    print(f"Video kit created at {output_dir}")


if __name__ == "__main__":
    main()
