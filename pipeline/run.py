from __future__ import annotations

import argparse
import hashlib
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
    NO_NOVEL_ESSAY_ANGLE,
    NO_RELEVANT_NEWS,
    NO_SOURCE_NEWS,
    SCRIPT_NOT_APPROVED,
    PipelineConfig,
    build_timeline_slots,
    evaluate_script_gate,
    expected_news_dates,
    is_retryable_exception,
    nearest_essay_similarity,
    timeline_duration_seconds,
)
from pipeline.credits import write_credits
from pipeline.media import download_shot_asset
from pipeline.news import NewsItem, parse_news_file
from pipeline.script_sections import SectionAlignmentError, parse_sectioned_script

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


def collect_available_news(
    news_dir: Path, target_date: date
) -> tuple[str, list[Path], list[date], list[NewsItem]]:
    available: list[Path] = []
    missing: list[date] = []
    items: list[NewsItem] = []
    for news_date in expected_news_dates(target_date):
        path = news_dir / f"{news_date.isoformat()}.txt"
        if not path.exists() or not path.read_text(encoding="utf-8").strip():
            missing.append(news_date)
            continue
        parsed = parse_news_file(path)
        if not parsed:
            raise ValueError(f"No structured news items parsed from {path}")
        available.append(path)
        items.extend(parsed)
    payload = {
        "schema_version": 1,
        "items": [item.model_dump() for item in items],
    }
    return json.dumps(payload, ensure_ascii=False), available, missing, items


def materialize_selection(
    decision: dict[str, Any], source_items: list[NewsItem]
) -> dict[str, Any]:
    catalog = {item.news_id: item for item in source_items}
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in decision.get("items", []) if isinstance(decision, dict) else []:
        if not isinstance(ref, dict):
            raise ValueError("Selector returned a non-object item reference")
        news_id = str(ref.get("news_id", "") or "").strip()
        if news_id not in catalog:
            raise ValueError(f"Selector referenced unknown news_id={news_id!r}")
        if news_id in seen:
            raise ValueError(f"Selector referenced duplicate news_id={news_id!r}")
        seen.add(news_id)
        record = catalog[news_id].model_dump()
        record["selection_reason"] = str(ref.get("selection_reason", "") or "").strip()
        selected.append(record)
    return {
        "items": selected,
        "discarded_duplicates": decision.get("discarded_duplicates", []),
        "selection_notes": decision.get("selection_notes", []),
    }


def load_selection_history(scripts_dir: Path, target_date: date, lookback_days: int) -> str:
    """Return the newest covered stories from approved episodes, never merely selected-but-unused items."""
    cutoff = target_date.fromordinal(target_date.toordinal() - max(1, lookback_days))
    items: list[dict[str, Any]] = []
    if not scripts_dir.exists():
        return "[]"

    episode_dirs = sorted((path for path in scripts_dir.iterdir() if path.is_dir()), reverse=True)
    for episode_dir in episode_dirs:
        try:
            episode_date = datetime.strptime(episode_dir.name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if episode_date >= target_date or episode_date < cutoff:
            continue

        selected_path = episode_dir / "selected_news.json"
        reviews_path = episode_dir / "reviews.json"
        plan_path = episode_dir / "episode_plan.json"
        try:
            reviews = json.loads(reviews_path.read_text(encoding="utf-8"))
            selected = json.loads(selected_path.read_text(encoding="utf-8"))
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # If an approved legacy episode has no plan, we cannot prove which selected items were narrated.
            # Skipping is safer than incorrectly burning stories that may never have appeared.
            continue
        if not bool(reviews.get("approved_for_multimedia", False)):
            continue

        selected_items = selected.get("items", []) if isinstance(selected, dict) else []
        covered_indices: list[int] = []
        beats = plan.get("beats", []) if isinstance(plan, dict) else []
        if beats:
            evidence_lookup: dict[str, int] = {}
            for evidence in plan.get("evidence", []) if isinstance(plan, dict) else []:
                if not isinstance(evidence, dict):
                    continue
                evidence_id = str(evidence.get("evidence_id", "") or "").strip()
                try:
                    selected_index = int(evidence.get("selected_news_index", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if evidence_id and selected_index >= 1:
                    evidence_lookup[evidence_id] = selected_index
            for beat in beats:
                if not isinstance(beat, dict):
                    continue
                for evidence_id in beat.get("evidence_ids", []):
                    index = evidence_lookup.get(str(evidence_id), 0)
                    if index >= 1 and index not in covered_indices:
                        covered_indices.append(index)
        else:
            # Transitional compatibility for approved pre-beat plans. Legacy/incomplete plans are already skipped above.
            for story in plan.get("stories", []) if isinstance(plan, dict) else []:
                if not isinstance(story, dict):
                    continue
                try:
                    index = int(story.get("selected_news_index", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if index >= 1 and index not in covered_indices:
                    covered_indices.append(index)

        for index in covered_indices:
            if not (1 <= index <= len(selected_items)):
                continue
            item = selected_items[index - 1]
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "title": item.get("title", ""),
                    "date": item.get("date", ""),
                    "source": item.get("source", ""),
                    "url": item.get("url", ""),
                    "summary": item.get("summary", ""),
                }
            )
            if len(items) >= 40:
                return json.dumps(items, ensure_ascii=False)

    return json.dumps(items, ensure_ascii=False)


def load_essay_history(
    scripts_dir: Path,
    target_date: date,
    lookback_days: int,
    max_items: int,
) -> list[dict[str, Any]]:
    """Load recent approved MODERN essay identities, including same-day canonical reruns.

    Legacy generations are deliberately excluded from editorial memory and future Voice DNA.
    A missing episode_plan.json is treated as legacy/incomplete rather than reconstructed from prose.
    """
    cutoff = target_date.fromordinal(target_date.toordinal() - max(1, lookback_days))
    essays: list[dict[str, Any]] = []
    if not scripts_dir.exists():
        return essays

    for episode_dir in sorted(
        (path for path in scripts_dir.iterdir() if path.is_dir()), reverse=True
    ):
        try:
            episode_date = datetime.strptime(episode_dir.name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if episode_date > target_date or episode_date < cutoff:
            continue

        reviews_path = episode_dir / "reviews.json"
        try:
            reviews = json.loads(reviews_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not bool(reviews.get("approved_for_multimedia", False)):
            continue

        legacy_path = episode_dir / "legacy.json"
        if legacy_path.exists():
            try:
                legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                legacy = {"exclude_from_essay_history": True}
            if bool(legacy.get("exclude_from_essay_history", True)):
                continue

        plan_path = episode_dir / "episode_plan.json"
        if not plan_path.exists():
            continue
        try:
            raw_plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(raw_plan, dict):
            continue
        plan: dict[str, Any] = raw_plan

        script_excerpt = ""
        script_path = episode_dir / "script.txt"
        if script_path.exists():
            try:
                script_excerpt = script_path.read_text(encoding="utf-8").strip()[:1600]
            except OSError:
                script_excerpt = ""

        essays.append(
            {
                "episode_date": episode_date.isoformat(),
                "topic_signature": str(plan.get("topic_signature") or ""),
                "central_question": str(plan.get("central_question") or ""),
                "thesis": str(plan.get("thesis") or ""),
                "narrative_lens": str(plan.get("narrative_lens") or ""),
                "hook": str(plan.get("hook") or ""),
                "script_excerpt": script_excerpt,
            }
        )
        if len(essays) >= max_items:
            break
    return essays


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
    evidence = plan.get("evidence", []) if isinstance(plan, dict) else []
    beats = plan.get("beats", []) if isinstance(plan, dict) else []
    if not evidence:
        raise ValueError("Editorial Director returned no evidence in episode_plan")
    if not beats:
        raise ValueError("Editorial Director returned no idea-led beats in episode_plan")

    evidence_indices: list[int] = []
    evidence_ids: list[str] = []
    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError("Every episode_plan evidence item must be an object")
        index = int(item.get("selected_news_index", 0) or 0)
        if index < 1 or index > selected_count:
            raise ValueError("episode_plan evidence references selected news outside the catalog")
        evidence_id = str(item.get("evidence_id", "") or "").strip()
        if not evidence_id:
            raise ValueError("Every episode_plan evidence item must have evidence_id")
        evidence_indices.append(index)
        evidence_ids.append(evidence_id)
    if len(evidence_indices) != len(set(evidence_indices)):
        raise ValueError("episode_plan.evidence must not duplicate selected news")
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("episode_plan.evidence must use unique evidence_id values")

    allowed = set(evidence_ids)
    used: set[str] = set()
    beat_ids: list[str] = []
    for beat in beats:
        if not isinstance(beat, dict):
            raise ValueError("Every episode_plan beat must be an object")
        beat_id = str(beat.get("beat_id", "") or "").strip()
        if not beat_id:
            raise ValueError("Every episode_plan beat must have beat_id")
        beat_ids.append(beat_id)
        refs = [str(value) for value in beat.get("evidence_ids", [])]
        if len(refs) != len(set(refs)):
            raise ValueError(f"Beat {beat_id} repeats an evidence_id")
        if set(refs) - allowed:
            raise ValueError(f"Beat {beat_id} references undeclared evidence_id values")
        used.update(refs)
    if len(beat_ids) != len(set(beat_ids)):
        raise ValueError("episode_plan beat_id values must be unique")
    if allowed - used:
        raise ValueError("Every declared evidence item must serve at least one beat")


def _script_sha256(script: str) -> str:
    normalized = " ".join(str(script or "").split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _candidate_rank(
    gate: dict[str, Any],
    editorial: dict[str, Any],
    seo: dict[str, Any],
    attention: dict[str, Any],
    voice: dict[str, Any],
) -> tuple[Any, ...]:
    checks = gate.get("checks", {}) if isinstance(gate, dict) else {}
    passed = sum(1 for value in checks.values() if bool(value))
    scores = [
        float(editorial.get("score", 0) or 0),
        float(seo.get("score", 0) or 0),
        float(attention.get("score", 0) or 0),
        float(voice.get("score", 0) or 0),
    ]
    factuality = {"low": 2, "medium": 1, "high": 0}.get(
        str(editorial.get("factuality_risk", "")).lower(), 0
    )
    ai_smell = {"low": 2, "medium": 1, "high": 0}.get(
        str(voice.get("ai_smell_risk", "")).lower(), 0
    )
    return (
        int(bool(gate.get("approved", False))),
        factuality,
        ai_smell,
        passed,
        min(scores),
        round(sum(scores) / len(scores), 4),
        float(voice.get("intellectual_depth", 0) or 0),
        float(voice.get("human_relevance", 0) or 0),
    )


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
        news_text, available_files, missing_dates, source_items = collect_available_news(news_dir, target_date)
        if not source_items:
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
        previous_essays = load_essay_history(
            history_scripts_root,
            target_date,
            CONFIG.essay_history_days,
            CONFIG.max_recent_essays,
        )
        previous_essays_json = json.dumps(previous_essays, ensure_ascii=False)

        selection_state = await run_agent(
            selector_agent,
            {"news_text": news_text, "previous_selected_news": previous_selected_news},
            "Select the unique, high-value AI developments for this episode.",
            step="select_news",
            trace=agent_trace,
        )
        selection_decision = SelectionResult.model_validate(
            selection_state.get("selected_news", {})
        ).model_dump()
        selection = materialize_selection(selection_decision, source_items)
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
        novelty_attempts: list[dict[str, Any]] = []
        novelty_feedback = ""
        episode_plan: dict[str, Any] | None = None

        for novelty_attempt in range(1, CONFIG.max_novelty_replans + 2):
            director_state = await run_agent(
                editorial_director_agent,
                {
                    "news_text": news_text,
                    "selected_news": selected_json,
                    "voice_profile": voice_profile,
                    "discourse_profile": discourse_profile,
                    "previous_essays": previous_essays_json,
                    "novelty_feedback": novelty_feedback,
                },
                (
                    "Design a novel episode thesis, evidence strategy, narrative beats, and target duration. "
                    "Do not repeat a recent essay merely with new headlines."
                ),
                step="plan_episode" if novelty_attempt == 1 else "replan_episode_novelty",
                trace=agent_trace,
                iteration=novelty_attempt,
            )
            candidate_plan = EpisodePlan.model_validate(
                director_state.get("episode_plan", {})
            ).model_dump()
            validate_episode_plan(candidate_plan, len(selection["items"]))
            candidate_topic = " ".join(
                str(candidate_plan.get(key, "") or "")
                for key in ("topic_signature", "central_question", "thesis", "narrative_lens")
            )
            nearest = nearest_essay_similarity(candidate_topic, previous_essays)
            similarity = float(nearest.get("similarity", 0)) if nearest else 0.0
            duplicate = bool(nearest and similarity >= CONFIG.essay_duplicate_threshold)
            novelty_attempts.append(
                {
                    "attempt": novelty_attempt,
                    "topic_signature": candidate_plan.get("topic_signature"),
                    "narrative_lens": candidate_plan.get("narrative_lens"),
                    "novelty_angle": candidate_plan.get("novelty_angle"),
                    "nearest_previous_essay": nearest,
                    "similarity": similarity,
                    "threshold": CONFIG.essay_duplicate_threshold,
                    "duplicate": duplicate,
                }
            )
            episode_plan = candidate_plan
            if not duplicate:
                break
            if novelty_attempt > CONFIG.max_novelty_replans:
                break
            novelty_feedback = json.dumps(
                {
                    "problem": "The proposed essay is too similar to a recent approved essay.",
                    "nearest_previous_essay": nearest,
                    "similarity": similarity,
                    "threshold": CONFIG.essay_duplicate_threshold,
                    "instruction": (
                        "Change the underlying question, mechanism, human stakes, historical mirror, or "
                        "narrative lens. Do not merely rephrase the current thesis."
                    ),
                },
                ensure_ascii=False,
            )

        if episode_plan is None:
            raise RuntimeError("Editorial Director did not produce an episode plan")

        write_json(
            episode_scripts_dir / "novelty_check.json",
            {
                "history_days": CONFIG.essay_history_days,
                "previous_essay_count": len(previous_essays),
                "threshold": CONFIG.essay_duplicate_threshold,
                "max_novelty_replans": CONFIG.max_novelty_replans,
                "attempts": novelty_attempts,
            },
        )
        final_novelty = novelty_attempts[-1]
        if final_novelty.get("duplicate"):
            write_json(episode_scripts_dir / "episode_plan.json", episode_plan)
            validation_warnings.append(
                "Editorial plan remained too similar to a recent approved essay after bounded replanning"
            )
            write_json(
                state_path,
                _run_state_payload(
                    target_date=target_date,
                    status=NO_NOVEL_ESSAY_ANGLE,
                    reason=(
                        "No sufficiently novel essay angle was found after bounded replanning; "
                        f"nearest similarity={final_novelty.get('similarity')}"
                    ),
                    started_at=started_at,
                    validation_warnings=validation_warnings,
                ),
            )
            return episode_scripts_dir

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
        sectioned_draft_script = str(writer_state.get("draft_script", "")).strip()
        if not sectioned_draft_script:
            raise RuntimeError("Writer did not produce draft_script")
        try:
            draft_script, script_alignment = parse_sectioned_script(
                sectioned_draft_script, episode_plan
            )
        except SectionAlignmentError as exc:
            raise RuntimeError(f"Writer section alignment invalid: {exc}") from exc

        final_editorial: dict[str, Any] = {}
        final_seo: dict[str, Any] = {}
        final_attention: dict[str, Any] = {}
        final_voice: dict[str, Any] = {}
        final_gate: dict[str, Any] = {}
        best_candidate: dict[str, Any] | None = None
        judged_hashes: set[str] = set()

        for iteration in range(1, CONFIG.max_refinement_iterations + 1):
            candidate_hash = _script_sha256(draft_script)
            if candidate_hash in judged_hashes:
                validation_warnings.append(
                    f"Stopped refinement before iteration {iteration}: script hash {candidate_hash[:12]} was already judged"
                )
                break
            judged_hashes.add(candidate_hash)

            review_base = {
                "draft_script": draft_script,
                "selected_news": selected_json,
                "news_text": news_text,
                "episode_plan": episode_plan_json,
                "voice_profile": voice_profile,
                "discourse_profile": discourse_profile,
            }
            editorial_state = await run_agent(
                reviewer_agent, review_base,
                "Evaluate factuality, conceptual rigor, and editorial quality.",
                step="editorial_judge", trace=agent_trace, iteration=iteration,
            )
            seo_state = await run_agent(
                seo_master_agent, review_base,
                "Evaluate discoverability without sacrificing rigor or voice.",
                step="seo_judge", trace=agent_trace, iteration=iteration,
            )
            attention_state = await run_agent(
                youtube_attention_master_agent, review_base,
                "Evaluate earned attention, progressive revelation, pacing, and CTA.",
                step="attention_judge", trace=agent_trace, iteration=iteration,
            )
            voice_state = await run_agent(
                voice_humanity_critic_agent, review_base,
                "Evaluate voice fidelity, intellectual depth, humanity, analogies, and AI smell.",
                step="voice_judge", trace=agent_trace, iteration=iteration,
            )

            editorial_result = ReviewResult.model_validate(editorial_state.get("review", {})).model_dump()
            seo_result = MasterJudgeResult.model_validate(seo_state.get("seo_review", {})).model_dump()
            attention_result = MasterJudgeResult.model_validate(attention_state.get("attention_review", {})).model_dump()
            voice_result = VoiceReviewResult.model_validate(voice_state.get("voice_review", {})).model_dump()
            gate_result = evaluate_script_gate(
                draft_script, editorial_result, seo_result, attention_result, voice_result, CONFIG
            )
            rank = _candidate_rank(gate_result, editorial_result, seo_result, attention_result, voice_result)
            candidate = {
                "iteration": iteration,
                "script_sha256": candidate_hash,
                "script": draft_script,
                "sectioned_script": sectioned_draft_script,
                "alignment": script_alignment,
                "editorial": editorial_result,
                "seo": seo_result,
                "attention": attention_result,
                "voice": voice_result,
                "gate": gate_result,
                "rank": rank,
            }
            became_best = best_candidate is None or rank > best_candidate["rank"]
            if became_best:
                best_candidate = candidate

            iteration_trace.append(
                {
                    "iteration": iteration,
                    "script_sha256": candidate_hash,
                    "selected_as_best_so_far": became_best,
                    "duration_seconds": gate_result["duration_seconds"],
                    "approved": gate_result["approved"],
                    "checks": gate_result["checks"],
                    "editorial_score": editorial_result["score"],
                    "seo_score": seo_result["score"],
                    "attention_score": attention_result["score"],
                    "voice_score": voice_result["score"],
                    "voice_fidelity": voice_result["voice_fidelity"],
                    "intellectual_depth": voice_result["intellectual_depth"],
                    "human_relevance": voice_result["human_relevance"],
                    "analogy_quality": voice_result["analogy_quality"],
                    "ai_smell_risk": voice_result["ai_smell_risk"],
                    "factuality_risk": editorial_result["factuality_risk"],
                }
            )
            if gate_result["approved"] or iteration == CONFIG.max_refinement_iterations:
                break

            refiner_state = await run_agent(
                refiner_agent,
                {
                    **review_base,
                    "sectioned_draft_script": sectioned_draft_script,
                    "review": json.dumps(editorial_result, ensure_ascii=False),
                    "seo_review": json.dumps(seo_result, ensure_ascii=False),
                    "attention_review": json.dumps(attention_result, ensure_ascii=False),
                    "voice_review": json.dumps(voice_result, ensure_ascii=False),
                },
                "Revise the script while preserving factuality, voice, depth, and the episode plan.",
                step="refine_script", trace=agent_trace, iteration=iteration,
            )
            refined = str(refiner_state.get("draft_script", "")).strip()
            if not refined:
                raise RuntimeError("Refiner did not produce draft_script")
            try:
                refined_script, refined_alignment = parse_sectioned_script(refined, episode_plan)
            except SectionAlignmentError as exc:
                validation_warnings.append(
                    f"Stopped refinement after iteration {iteration}: refiner returned invalid section markers: {exc}"
                )
                break
            refined_hash = _script_sha256(refined_script)
            if refined_hash in judged_hashes:
                validation_warnings.append(
                    f"Stopped refinement after iteration {iteration}: refiner produced an already-judged script hash {refined_hash[:12]}"
                )
                break
            sectioned_draft_script = refined
            draft_script = refined_script
            script_alignment = refined_alignment

        if best_candidate is None:
            raise RuntimeError("No judged script candidate was produced")
        draft_script = best_candidate["script"]
        sectioned_draft_script = best_candidate["sectioned_script"]
        script_alignment = best_candidate["alignment"]
        final_editorial = best_candidate["editorial"]
        final_seo = best_candidate["seo"]
        final_attention = best_candidate["attention"]
        final_voice = best_candidate["voice"]
        final_gate = best_candidate["gate"]
        best_iteration = int(best_candidate["iteration"])
        best_script_sha256 = str(best_candidate["script_sha256"])

        (episode_scripts_dir / "script.txt").write_text(
            draft_script + "\n", encoding="utf-8"
        )
        write_json(episode_scripts_dir / "script_sections.json", script_alignment)
        write_json(
            episode_scripts_dir / "reviews.json",
            {
                "approved_for_multimedia": bool(final_gate.get("approved", False)),
                "gate": final_gate,
                "refinement_iterations": iteration_trace,
                "best_candidate": {
                    "iteration": best_iteration,
                    "script_sha256": best_script_sha256,
                    "judged_unique_script_count": len(judged_hashes),
                },
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
                        logical_file=f"assets/{destination.name}",
                    )
                )
        write_json(episode_media_dir / "manifest.json", manifest)
        write_credits(manifest, episode_media_dir)
        write_json(
            state_path,
            _run_state_payload(
                target_date=target_date,
                status=APPROVED,
                reason="All deterministic, factual, narrative, voice, novelty, and quality gates passed",
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