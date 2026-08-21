from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.core import (
    FAILURE,
    KNOWN_STATUSES,
    NO_SOURCE_NEWS,
    PipelineConfig,
    estimate_spoken_duration_seconds,
    expected_news_dates,
)

CONFIG = PipelineConfig.from_env()


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def source_window(news_dir: Path, target_date: date) -> dict[str, Any]:
    expected = expected_news_dates(target_date)
    files: list[dict[str, Any]] = []
    missing: list[str] = []
    for item_date in expected:
        path = news_dir / f"{item_date.isoformat()}.txt"
        text = read_text(path)
        if text:
            files.append(
                {
                    "name": path.name,
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size if path.exists() else None,
                }
            )
        else:
            missing.append(item_date.isoformat())
    return {
        "expected_dates": [item.isoformat() for item in expected],
        "available_files": files,
        "missing_dates": missing,
    }


def meaningful_duplicates(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        normalized = text.lower()
        if normalized.startswith(("ninguna", "ninguno", "none", "no duplicate", "sin duplic")):
            continue
        result.append(text)
    return result


def score_block(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "approved": bool(payload.get("approved", False)),
        "score": payload.get("score"),
        "problems": payload.get("problems", []),
        "improvements": payload.get("improvements", []),
    }


def artifact_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size if path.exists() and path.is_file() else None,
    }


def summarize_trace(trace: dict[str, Any]) -> dict[str, Any]:
    calls = trace.get("agent_calls", []) if isinstance(trace, dict) else []
    iterations = trace.get("refinement_iterations", []) if isinstance(trace, dict) else []
    total_usage = {
        "prompt_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
    }
    for call in calls:
        if not isinstance(call, dict):
            continue
        usage = call.get("usage", {})
        if isinstance(usage, dict):
            for key in total_usage:
                value = usage.get(key)
                if isinstance(value, int):
                    total_usage[key] += value
    successful_calls = [
        call for call in calls if isinstance(call, dict) and call.get("status") == "success"
    ]
    retries = [
        call
        for call in calls
        if isinstance(call, dict) and int(call.get("attempt", 1) or 1) > 1
    ]
    failed_attempts = [
        call for call in calls if isinstance(call, dict) and call.get("status") == "error"
    ]
    return {
        "agent_attempts": len(calls),
        "successful_agent_calls": len(successful_calls),
        "retry_attempts": len(retries),
        "failed_attempts": len(failed_attempts),
        "token_usage": total_usage,
        "refinement_iterations": iterations,
        "validation_warnings": trace.get("validation_warnings", [])
        if isinstance(trace, dict)
        else [],
    }


def infer_status(run_state: dict[str, Any], build_outcome: str, sources: dict[str, Any]) -> str:
    state_status = (
        str(run_state.get("status", "")).strip().lower()
        if isinstance(run_state, dict)
        else ""
    )
    if state_status in KNOWN_STATUSES:
        return state_status
    normalized = build_outcome.strip().lower()
    if normalized in KNOWN_STATUSES:
        return normalized
    if not sources["available_files"]:
        return NO_SOURCE_NEWS
    return FAILURE


def build_report(
    target_date: date,
    news_dir: Path,
    scripts_root: Path,
    multimedia_root: Path,
    build_outcome: str,
    editorial_dir: Path = Path("editorial"),
) -> dict[str, Any]:
    episode = target_date.isoformat()
    scripts_dir = scripts_root / episode
    multimedia_dir = multimedia_root / episode

    selected = read_json(scripts_dir / "selected_news.json", {})
    episode_plan = read_json(scripts_dir / "episode_plan.json", {})
    novelty_check = read_json(scripts_dir / "novelty_check.json", {})
    reviews = read_json(scripts_dir / "reviews.json", {})
    run_state = read_json(scripts_dir / "run_state.json", {})
    trace = read_json(scripts_dir / "execution_trace.json", {})
    media_plan = read_json(multimedia_dir / "plan.json", {})
    manifest = read_json(multimedia_dir / "manifest.json", [])
    script = read_text(scripts_dir / "script.txt")

    selected_items = selected.get("items", []) if isinstance(selected, dict) else []
    duplicates = meaningful_duplicates(
        selected.get("discarded_duplicates", []) if isinstance(selected, dict) else []
    )
    planned_stories = episode_plan.get("stories", []) if isinstance(episode_plan, dict) else []
    novelty_attempts = (
        novelty_check.get("attempts", []) if isinstance(novelty_check, dict) else []
    )
    final_novelty = (
        novelty_attempts[-1]
        if isinstance(novelty_attempts, list) and novelty_attempts
        else {}
    )
    segments = media_plan.get("segments", []) if isinstance(media_plan, dict) else []
    media_segments = [segment for segment in segments if segment.get("mode") == "media"]
    presenter_segments = [
        segment for segment in segments if segment.get("mode") == "presenter"
    ]
    fallback_assets = (
        [
            item
            for item in manifest
            if isinstance(item, dict) and item.get("provider") == "generated_fallback"
        ]
        if isinstance(manifest, list)
        else []
    )

    editorial = reviews.get("editorial", {}) if isinstance(reviews, dict) else {}
    seo = reviews.get("seo_master", {}) if isinstance(reviews, dict) else {}
    attention = (
        reviews.get("youtube_attention_master", {}) if isinstance(reviews, dict) else {}
    )
    voice = reviews.get("voice_humanity", {}) if isinstance(reviews, dict) else {}
    gate = reviews.get("gate", {}) if isinstance(reviews, dict) else {}
    approved = (
        bool(reviews.get("approved_for_multimedia", False))
        if isinstance(reviews, dict)
        else False
    )
    sources = source_window(news_dir, target_date)
    estimated_duration = (
        estimate_spoken_duration_seconds(script, CONFIG) if script else None
    )
    status = infer_status(run_state, build_outcome, sources)

    artifacts = {
        "run_state": artifact_record(scripts_dir / "run_state.json"),
        "execution_trace": artifact_record(scripts_dir / "execution_trace.json"),
        "selected_news": artifact_record(scripts_dir / "selected_news.json"),
        "episode_plan": artifact_record(scripts_dir / "episode_plan.json"),
        "novelty_check": artifact_record(scripts_dir / "novelty_check.json"),
        "reviews": artifact_record(scripts_dir / "reviews.json"),
        "script": artifact_record(scripts_dir / "script.txt"),
        "multimedia_plan": artifact_record(multimedia_dir / "plan.json"),
        "multimedia_manifest": artifact_record(multimedia_dir / "manifest.json"),
        "voice_profile": artifact_record(editorial_dir / "voice_profile.md"),
        "discourse_profile": artifact_record(editorial_dir / "discourse_profile.md"),
    }

    return {
        "schema_version": 5,
        "episode_date": episode,
        "run_id": os.getenv("EPISODE_RUN_ID") or os.getenv("GITHUB_RUN_ID"),
        "git_sha": os.getenv("GITHUB_SHA"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "build_outcome": build_outcome,
        "state": run_state,
        "source_window": sources,
        "configuration": CONFIG.as_report_dict(),
        "selection": {
            "selected_count": len(selected_items),
            "selected_titles": [
                item.get("title", "") for item in selected_items if isinstance(item, dict)
            ],
            "discarded_duplicates_count": len(duplicates),
            "discarded_duplicates": duplicates,
        },
        "editorial_direction": {
            "topic_signature": episode_plan.get("topic_signature")
            if isinstance(episode_plan, dict)
            else None,
            "narrative_lens": episode_plan.get("narrative_lens")
            if isinstance(episode_plan, dict)
            else None,
            "novelty_angle": episode_plan.get("novelty_angle")
            if isinstance(episode_plan, dict)
            else None,
            "historical_mirror": episode_plan.get("historical_mirror")
            if isinstance(episode_plan, dict)
            else None,
            "evidence_strategy": episode_plan.get("evidence_strategy")
            if isinstance(episode_plan, dict)
            else None,
            "central_question": episode_plan.get("central_question")
            if isinstance(episode_plan, dict)
            else None,
            "thesis": episode_plan.get("thesis")
            if isinstance(episode_plan, dict)
            else None,
            "hook": episode_plan.get("hook")
            if isinstance(episode_plan, dict)
            else None,
            "target_duration_minutes": episode_plan.get("target_duration_minutes")
            if isinstance(episode_plan, dict)
            else None,
            "planned_story_count": len(planned_stories),
            "closing_question": episode_plan.get("closing_question")
            if isinstance(episode_plan, dict)
            else None,
        },
        "novelty": {
            "history_days": novelty_check.get("history_days")
            if isinstance(novelty_check, dict)
            else None,
            "previous_essay_count": novelty_check.get("previous_essay_count", 0)
            if isinstance(novelty_check, dict)
            else 0,
            "threshold": novelty_check.get("threshold")
            if isinstance(novelty_check, dict)
            else None,
            "planning_attempts": len(novelty_attempts)
            if isinstance(novelty_attempts, list)
            else 0,
            "final_similarity": final_novelty.get("similarity")
            if isinstance(final_novelty, dict)
            else None,
            "duplicate": final_novelty.get("duplicate")
            if isinstance(final_novelty, dict)
            else None,
            "nearest_previous_essay": final_novelty.get("nearest_previous_essay")
            if isinstance(final_novelty, dict)
            else None,
        },
        "script": {
            "exists": bool(script),
            "word_count": len(script.split()) if script else 0,
            "estimated_duration_seconds": estimated_duration,
            "within_target_duration": bool(
                estimated_duration is not None
                and CONFIG.target_min_seconds
                <= estimated_duration
                <= CONFIG.target_max_seconds
            ),
            "approved_for_multimedia": approved,
            "gate": gate,
        },
        "judges": {
            "editorial": {
                **score_block(editorial),
                "factuality_risk": editorial.get("factuality_risk"),
            },
            "seo_master": score_block(seo),
            "youtube_attention_master": score_block(attention),
            "voice_humanity": {
                **score_block(voice),
                "voice_fidelity": voice.get("voice_fidelity"),
                "intellectual_depth": voice.get("intellectual_depth"),
                "human_relevance": voice.get("human_relevance"),
                "analogy_quality": voice.get("analogy_quality"),
                "ai_smell_risk": voice.get("ai_smell_risk"),
            },
        },
        "observability": summarize_trace(trace),
        "multimedia": {
            "plan_exists": bool(segments),
            "total_slots": len(segments),
            "media_slots": len(media_segments),
            "presenter_slots": len(presenter_segments),
            "downloaded_assets": len(manifest) if isinstance(manifest, list) else 0,
            "fallback_assets": len(fallback_assets),
            "provider_errors": (
                sum(
                    len(item.get("errors", []))
                    for item in manifest
                    if isinstance(item, dict)
                    and isinstance(item.get("errors", []), list)
                )
                if isinstance(manifest, list)
                else 0
            ),
        },
        "artifacts": artifacts,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an episode run_report.json")
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--build-outcome", default="success")
    parser.add_argument("--news-dir", default="news")
    parser.add_argument("--scripts-dir", default="scripts")
    parser.add_argument("--multimedia-dir", default="multimedia")
    parser.add_argument("--editorial-dir", default="editorial")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target_date = parse_date(args.target_date)
    scripts_root = Path(args.scripts_dir)
    output_dir = scripts_root / target_date.isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)
    report = build_report(
        target_date=target_date,
        news_dir=Path(args.news_dir),
        scripts_root=scripts_root,
        multimedia_root=Path(args.multimedia_dir),
        build_outcome=args.build_outcome,
        editorial_dir=Path(args.editorial_dir),
    )
    output_path = output_dir / "run_report.json"
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Run report created at {output_path}")
    print(
        json.dumps(
            {"status": report["status"], "episode_date": report["episode_date"]}
        )
    )


if __name__ == "__main__":
    main()
