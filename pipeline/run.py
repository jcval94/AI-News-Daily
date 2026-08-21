from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agent import (
    EpisodePlan,
    MasterJudgeResult,
    MultimediaPlan,
    ReviewResult,
    SelectionResult,
    VoiceReviewResult,
    editorial_director_agent,
    multimedia_editor_agent,
    refiner_agent,
    reviewer_agent,
    selector_agent,
    seo_master_agent,
    voice_humanity_critic_agent,
    writer_agent,
    youtube_attention_master_agent,
)
from pipeline.core import (
    APPROVED,
    FAILURE,
    NO_RELEVANT_NEWS,
    NO_SOURCE_NEWS,
    SCRIPT_NOT_APPROVED,
    PipelineConfig,
    build_timeline_slots,
    evaluate_script_gate,
    expected_news_dates,
    is_retryable_exception,
    timeline_duration_seconds,
)
from pipeline.media import download_shot_asset

APP_NAME = "ai_news_daily_video"
USER_ID = "github_actions"
CONFIG = PipelineConfig.from_env()
DOWNLOAD_MULTIMEDIA = os.getenv("DOWNLOAD_MULTIMEDIA", "true").strip().lower() not in {
    "0",
    "false",
    "no",
}


def parse_target_date(value: str | None) -> date:
    if value:
        return datetime.strptime(value, "%Y-%m-%d").date()
    return date.today()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collect_available_news(news_dir: Path, target_date: date) -> tuple[str, list[Path], list[date]]:
    available: list[Path] = []
    missing: list[date] = []
    sections: list[str] = []
    for news_date in expected_news_dates(target_date):
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
            f"===== SOURCE NEWS FILE: {path.name} =====\n{text}\n===== END SOURCE: {path.name} ====="
        )
    return "\n\n".join(sections), available, missing


def load_selection_history(scripts_dir: Path, target_date: date, lookback_days: int) -> str:
    cutoff = target_date.fromordinal(target_date.toordinal() - max(1, lookback_days))
    items: list[dict[str, Any]] = []
    if not scripts_dir.exists():
        return "[]"

    for selected_path in sorted(scripts_dir.glob("*/selected_news.json"), reverse=True):
        try:
            episode_date = datetime.strptime(selected_path.parent.name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if episode_date >= target_date or episode_date < cutoff:
            continue
        reviews_path = selected_path.parent / "reviews.json"
        try:
            reviews = json.loads(reviews_path.read_text(encoding="utf-8"))
            selected = json.loads(selected_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not bool(reviews.get("approved_for_multimedia", False)):
            continue
        for item in selected.get("items", []):
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


def load_editorial_profiles(editorial_dir: Path) -> tuple[str, str]:
    voice_path = editorial_dir / "voice_profile.md"
    discourse_path = editorial_dir / "discourse_profile.md"
    try:
        voice_profile = voice_path.read_text(encoding="utf-8").strip()
        discourse_profile = discourse_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"Editorial profile could not be loaded: {exc}") from exc
    if not voice_profile or not discourse_profile:
        raise RuntimeError("Editorial voice/discourse profiles must not be empty")
    return voice_profile, discourse_profile


def validate_episode_plan(plan: dict[str, Any], selected_count: int) -> None:
    stories = plan.get("stories", []) if isinstance(plan, dict) else []
    if not stories:
        raise ValueError("Editorial Director returned no stories in episode_plan")
    indices = [int(story.get("selected_news_index", 0)) for story in stories if isinstance(story, dict)]
    if len(indices) != len(stories):
        raise ValueError("Every episode_plan story must be an object with selected_news_index")
    if any(index < 1 or index > selected_count for index in indices):
        raise ValueError("episode_plan references a selected_news_index outside selected news")
    if len(indices) != len(set(indices)):
        raise ValueError("episode_plan must not schedule the same selected story twice")


def _usage_from_event(event: Any) -> dict[str, int]:
    meta = getattr(event, "usage_metadata", None)
    if not meta:
        return {}
    result: dict[str, int] = {}
    for source, target in (
        ("prompt_token_count", "prompt_tokens"),
        ("candidates_token_count", "output_tokens"),
        ("thoughts_token_count", "reasoning_tokens"),
        ("total_token_count", "total_tokens"),
    ):
        value = getattr(meta, source, None)
        if isinstance(value, int):
            result[target] = value
    return result


def _merge_usage(total: dict[str, int], addition: dict[str, int]) -> None:
    for key, value in addition.items():
        total[key] = total.get(key, 0) + value


async def _run_agent_once(
    agent: Any, initial_state: dict[str, Any], prompt: str
) -> tuple[dict[str, Any], dict[str, int]]:
    service = InMemorySessionService()
    session_id = uuid.uuid4().hex
    await service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=session_id,
        state=initial_state,
    )
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=service)
    message = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    usage: dict[str, int] = {}
    seen_usage_event_ids: set[str] = set()
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session_id,
        new_message=message,
    ):
        event_id = str(getattr(event, "id", ""))
        event_usage = _usage_from_event(event)
        if event_usage and event_id not in seen_usage_event_ids:
            _merge_usage(usage, event_usage)
            if event_id:
                seen_usage_event_ids.add(event_id)

    session = await service.get_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=session_id,
    )
    if session is None:
        raise RuntimeError("ADK session disappeared unexpectedly")
    return dict(session.state), usage


async def run_agent(
    agent: Any,
    initial_state: dict[str, Any],
    prompt: str,
    *,
    step: str,
    trace: list[dict[str, Any]],
    iteration: int | None = None,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, CONFIG.agent_max_attempts + 1):
        started = time.monotonic()
        try:
            state, usage = await _run_agent_once(agent, initial_state, prompt)
            trace.append(
                {
                    "step": step,
                    "agent": getattr(agent, "name", type(agent).__name__),
                    "iteration": iteration,
                    "attempt": attempt,
                    "status": "success",
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "usage": usage,
                }
            )
            return state
        except Exception as exc:
            last_error = exc
            retryable = is_retryable_exception(exc)
            trace.append(
                {
                    "step": step,
                    "agent": getattr(agent, "name", type(agent).__name__),
                    "iteration": iteration,
                    "attempt": attempt,
                    "status": "error",
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "retryable": retryable,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1000],
                }
            )
            if not retryable or attempt >= CONFIG.agent_max_attempts:
                raise
            delay = CONFIG.agent_retry_base_seconds * (2 ** (attempt - 1))
            print(
                f"Transient failure in {step}; retrying in {delay:.1f}s: "
                f"{type(exc).__name__}: {exc}"
            )
            await asyncio.sleep(delay)

    assert last_error is not None
    raise last_error


def normalize_multimedia_plan(
    raw_plan: dict[str, Any],
    timeline_slots: list[dict[str, Any]],
    max_media_downloads: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    valid_slots = {slot["slot_number"]: slot for slot in timeline_slots}
    normalized_by_slot: dict[int, dict[str, Any]] = {}
    warnings: list[str] = []

    for raw in raw_plan.get("segments", []) if isinstance(raw_plan, dict) else []:
        if not isinstance(raw, dict):
            warnings.append("Ignored a non-object multimedia segment")
            continue
        try:
            number = int(raw.get("slot_number"))
        except (TypeError, ValueError):
            warnings.append("Ignored multimedia segment without a valid slot_number")
            continue
        if number not in valid_slots:
            warnings.append(f"Ignored multimedia segment for unknown slot {number}")
            continue
        query = str(raw.get("visual_query", "")).strip()
        if not query:
            warnings.append(f"Ignored media slot {number} because visual_query was empty")
            continue
        if number in normalized_by_slot:
            warnings.append(f"Duplicate media slot {number}; kept the last decision")
        slot = valid_slots[number]
        normalized_by_slot[number] = {
            **slot,
            "mode": "media",
            "visual_query": query,
            "on_screen_text": str(raw.get("on_screen_text", "")).strip()[:80],
            "reason": str(raw.get("reason", "")).strip(),
        }

    selected_numbers = sorted(normalized_by_slot)[: max(0, max_media_downloads)]
    if len(normalized_by_slot) > len(selected_numbers):
        warnings.append(
            f"Media plan exceeded MAX_MEDIA_DOWNLOADS={max_media_downloads}; excess slots were dropped"
        )

    selected = {number: normalized_by_slot[number] for number in selected_numbers}
    plan: list[dict[str, Any]] = []
    for slot in timeline_slots:
        media = selected.get(slot["slot_number"])
        if media:
            plan.append(media)
        else:
            plan.append(
                {
                    **slot,
                    "mode": "presenter",
                    "visual_query": "",
                    "on_screen_text": "",
                    "reason": "",
                }
            )
    return plan, warnings


def _run_state_payload(
    *,
    target_date: date,
    status: str,
    reason: str,
    started_at: str,
    approved: bool = False,
    refinement_iterations: int = 0,
    validation_warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "episode_date": target_date.isoformat(),
        "status": status,
        "publishable": approved,
        "reason": reason,
        "started_at_utc": started_at,
        "finished_at_utc": utc_now(),
        "refinement_iterations": refinement_iterations,
        "validation_warnings": validation_warnings or [],
    }


async def build(
    target_date: date,
    news_dir: Path,
    scripts_root: Path,
    multimedia_root: Path,
    history_scripts_root: Path,
    max_media_downloads: int,
    download_multimedia: bool,
    editorial_dir: Path = Path("editorial"),
) -> Path | None:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY before running the pipeline")

    started_at = utc_now()
    episode_scripts_dir = scripts_root / target_date.isoformat()
    episode_media_dir = multimedia_root / target_date.isoformat()
    episode_scripts_dir.mkdir(parents=True, exist_ok=True)
    state_path = episode_scripts_dir / "run_state.json"
    trace_path = episode_scripts_dir / "execution_trace.json"
    agent_trace: list[dict[str, Any]] = []
    iteration_trace: list[dict[str, Any]] = []
    validation_warnings: list[str] = []

    try:
        voice_profile, discourse_profile = load_editorial_profiles(editorial_dir)
        news_text, available_files, missing_dates = collect_available_news(news_dir, target_date)
        if not news_text:
            write_json(
                state_path,
                _run_state_payload(
                    target_date=target_date,
                    status=NO_SOURCE_NEWS,
                    reason="No usable source news in the editorial window",
                    started_at=started_at,
                ),
            )
            return episode_scripts_dir

        previous_selected_news = load_selection_history(
            history_scripts_root, target_date, CONFIG.selection_history_days
        )
        selection_state = await run_agent(
            selector_agent,
            {"news_text": news_text, "previous_selected_news": previous_selected_news},
            "Select the unique, high-value AI developments for this episode.",
            step="select_news",
            trace=agent_trace,
        )
        selection = SelectionResult.model_validate(
            selection_state.get("selected_news", {})
        ).model_dump()
        write_json(episode_scripts_dir / "selected_news.json", selection)
        if not selection["items"]:
            write_json(
                state_path,
                _run_state_payload(
                    target_date=target_date,
                    status=NO_RELEVANT_NEWS,
                    reason="Selector returned zero publishable stories",
                    started_at=started_at,
                ),
            )
            return episode_scripts_dir

        selected_json = json.dumps(selection, ensure_ascii=False)
        director_state = await run_agent(
            editorial_director_agent,
            {
                "news_text": news_text,
                "selected_news": selected_json,
                "voice_profile": voice_profile,
                "discourse_profile": discourse_profile,
            },
            "Design the episode thesis, story roles, narrative beats, and target duration.",
            step="plan_episode",
            trace=agent_trace,
        )
        episode_plan = EpisodePlan.model_validate(
            director_state.get("episode_plan", {})
        ).model_dump()
        validate_episode_plan(episode_plan, len(selection["items"]))
        write_json(episode_scripts_dir / "episode_plan.json", episode_plan)
        episode_plan_json = json.dumps(episode_plan, ensure_ascii=False)

        writer_state = await run_agent(
            writer_agent,
            {
                "news_text": news_text,
                "selected_news": selected_json,
                "episode_plan": episode_plan_json,
                "voice_profile": voice_profile,
                "discourse_profile": discourse_profile,
            },
            "Write the finished 7-20 minute Spanish reflective AI essay.",
            step="write_script",
            trace=agent_trace,
        )
        draft_script = str(writer_state.get("draft_script", "")).strip()
        if not draft_script:
            raise RuntimeError("Writer did not produce draft_script")

        final_editorial: dict[str, Any] = {}
        final_seo: dict[str, Any] = {}
        final_attention: dict[str, Any] = {}
        final_voice: dict[str, Any] = {}
        final_gate: dict[str, Any] = {}

        for iteration in range(1, CONFIG.max_refinement_iterations + 1):
            review_base = {
                "draft_script": draft_script,
                "selected_news": selected_json,
                "news_text": news_text,
                "episode_plan": episode_plan_json,
                "voice_profile": voice_profile,
                "discourse_profile": discourse_profile,
            }
            editorial_state = await run_agent(
                reviewer_agent,
                review_base,
                "Evaluate factuality, conceptual rigor, and editorial quality.",
                step="editorial_judge",
                trace=agent_trace,
                iteration=iteration,
            )
            seo_state = await run_agent(
                seo_master_agent,
                review_base,
                "Evaluate discoverability without sacrificing rigor or voice.",
                step="seo_judge",
                trace=agent_trace,
                iteration=iteration,
            )
            attention_state = await run_agent(
                youtube_attention_master_agent,
                review_base,
                "Evaluate earned attention, progressive revelation, pacing, and CTA.",
                step="attention_judge",
                trace=agent_trace,
                iteration=iteration,
            )
            voice_state = await run_agent(
                voice_humanity_critic_agent,
                review_base,
                "Evaluate voice fidelity, intellectual depth, humanity, analogies, and AI smell.",
                step="voice_judge",
                trace=agent_trace,
                iteration=iteration,
            )

            final_editorial = ReviewResult.model_validate(
                editorial_state.get("review", {})
            ).model_dump()
            final_seo = MasterJudgeResult.model_validate(
                seo_state.get("seo_review", {})
            ).model_dump()
            final_attention = MasterJudgeResult.model_validate(
                attention_state.get("attention_review", {})
            ).model_dump()
            final_voice = VoiceReviewResult.model_validate(
                voice_state.get("voice_review", {})
            ).model_dump()

            final_gate = evaluate_script_gate(
                draft_script,
                final_editorial,
                final_seo,
                final_attention,
                final_voice,
                CONFIG,
            )
            iteration_trace.append(
                {
                    "iteration": iteration,
                    "duration_seconds": final_gate["duration_seconds"],
                    "approved": final_gate["approved"],
                    "checks": final_gate["checks"],
                    "editorial_score": final_editorial["score"],
                    "seo_score": final_seo["score"],
                    "attention_score": final_attention["score"],
                    "voice_score": final_voice["score"],
                    "voice_fidelity": final_voice["voice_fidelity"],
                    "intellectual_depth": final_voice["intellectual_depth"],
                    "human_relevance": final_voice["human_relevance"],
                    "analogy_quality": final_voice["analogy_quality"],
                    "ai_smell_risk": final_voice["ai_smell_risk"],
                    "factuality_risk": final_editorial["factuality_risk"],
                }
            )
            if final_gate["approved"]:
                break
            if iteration == CONFIG.max_refinement_iterations:
                break

            refiner_state = await run_agent(
                refiner_agent,
                {
                    **review_base,
                    "review": json.dumps(final_editorial, ensure_ascii=False),
                    "seo_review": json.dumps(final_seo, ensure_ascii=False),
                    "attention_review": json.dumps(final_attention, ensure_ascii=False),
                    "voice_review": json.dumps(final_voice, ensure_ascii=False),
                },
                "Revise the script while preserving factuality, voice, depth, and the episode plan.",
                step="refine_script",
                trace=agent_trace,
                iteration=iteration,
            )
            refined = str(refiner_state.get("draft_script", "")).strip()
            if not refined:
                raise RuntimeError("Refiner did not produce draft_script")
            draft_script = refined

        (episode_scripts_dir / "script.txt").write_text(
            draft_script + "\n", encoding="utf-8"
        )
        write_json(
            episode_scripts_dir / "reviews.json",
            {
                "approved_for_multimedia": bool(final_gate.get("approved", False)),
                "gate": final_gate,
                "refinement_iterations": iteration_trace,
                "editorial": final_editorial,
                "seo_master": final_seo,
                "youtube_attention_master": final_attention,
                "voice_humanity": final_voice,
                "source_files": [path.name for path in available_files],
                "missing_dates": [item.isoformat() for item in missing_dates],
            },
        )

        if not final_gate.get("approved", False):
            write_json(
                state_path,
                _run_state_payload(
                    target_date=target_date,
                    status=SCRIPT_NOT_APPROVED,
                    reason=(
                        "The script exhausted refinement without passing every deterministic, "
                        "factual, attention, SEO, and voice gate"
                    ),
                    started_at=started_at,
                    refinement_iterations=len(iteration_trace),
                ),
            )
            return episode_scripts_dir

        timeline_duration = timeline_duration_seconds(draft_script, CONFIG)
        timeline_slots = build_timeline_slots(timeline_duration, CONFIG)
        editor_state = await run_agent(
            multimedia_editor_agent,
            {
                "final_script": draft_script,
                "episode_plan": episode_plan_json,
                "timeline_slots": json.dumps(timeline_slots, ensure_ascii=False),
                "max_media_downloads": max(0, max_media_downloads),
            },
            "Choose only the timeline slots where external media adds real explanatory value.",
            step="plan_multimedia",
            trace=agent_trace,
        )
        raw_plan = MultimediaPlan.model_validate(
            editor_state.get("multimedia_plan", {})
        ).model_dump()
        multimedia_plan, media_warnings = normalize_multimedia_plan(
            raw_plan, timeline_slots, max(0, max_media_downloads)
        )
        validation_warnings.extend(media_warnings)
        write_json(
            episode_media_dir / "plan.json",
            {
                "script_date": target_date.isoformat(),
                "spoken_duration_seconds": final_gate["duration_seconds"],
                "timeline_duration_seconds": timeline_duration,
                "first_15_seconds_slot_size": CONFIG.first_15_slot_seconds,
                "normal_slot_size": CONFIG.normal_slot_seconds,
                "max_media_downloads": max(0, max_media_downloads),
                "validation_warnings": media_warnings,
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
        write_json(episode_media_dir / "manifest.json", manifest)
        write_json(
            state_path,
            _run_state_payload(
                target_date=target_date,
                status=APPROVED,
                reason="All deterministic, factual, narrative, voice, and quality gates passed",
                started_at=started_at,
                approved=True,
                refinement_iterations=len(iteration_trace),
                validation_warnings=validation_warnings,
            ),
        )
        return episode_scripts_dir

    except Exception as exc:
        write_json(
            state_path,
            _run_state_payload(
                target_date=target_date,
                status=FAILURE,
                reason=f"{type(exc).__name__}: {str(exc)[:1000]}",
                started_at=started_at,
                refinement_iterations=len(iteration_trace),
                validation_warnings=validation_warnings,
            ),
        )
        raise
    finally:
        write_json(
            trace_path,
            {
                "schema_version": 2,
                "episode_date": target_date.isoformat(),
                "agent_calls": agent_trace,
                "refinement_iterations": iteration_trace,
                "validation_warnings": validation_warnings,
                "finished_at_utc": utc_now(),
            },
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the Tuesday/Friday AI-news production kit"
    )
    parser.add_argument(
        "--target-date", default=None, help="YYYY-MM-DD; must be Tuesday or Friday"
    )
    parser.add_argument("--news-dir", default="news")
    parser.add_argument("--scripts-dir", default="scripts")
    parser.add_argument("--multimedia-dir", default="multimedia")
    parser.add_argument("--history-scripts-dir", default="scripts")
    parser.add_argument("--editorial-dir", default="editorial")
    parser.add_argument(
        "--max-media-downloads", type=int, default=CONFIG.max_media_downloads
    )
    parser.add_argument("--no-download-multimedia", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(
        build(
            target_date=parse_target_date(args.target_date),
            news_dir=Path(args.news_dir),
            scripts_root=Path(args.scripts_dir),
            multimedia_root=Path(args.multimedia_dir),
            history_scripts_root=Path(args.history_scripts_dir),
            max_media_downloads=args.max_media_downloads,
            download_multimedia=DOWNLOAD_MULTIMEDIA and not args.no_download_multimedia,
            editorial_dir=Path(args.editorial_dir),
        )
    )


if __name__ == "__main__":
    main()
