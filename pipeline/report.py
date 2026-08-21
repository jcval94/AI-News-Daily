from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

WORDS_PER_SECOND = float(os.getenv("WORDS_PER_SECOND", "2.5"))
FIRST_15_SLOT_SECONDS = 3
NORMAL_SLOT_SECONDS = 4


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def expected_news_dates(target_date: date) -> list[date]:
    if target_date.weekday() == 1:  # Tuesday -> Friday, Saturday, Sunday, Monday
        offsets = (4, 3, 2, 1)
    elif target_date.weekday() == 4:  # Friday -> Tuesday, Wednesday, Thursday
        offsets = (3, 2, 1)
    else:
        raise ValueError(
            f"Run reports are only defined for Tuesday/Friday episodes; got {target_date.isoformat()}"
        )
    return [target_date - timedelta(days=offset) for offset in offsets]


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
    return path.read_text(encoding="utf-8").strip()


def estimate_duration_seconds(script: str) -> int | None:
    if not script:
        return None
    words = max(1, len(script.split()))
    raw = max(60.0, min(100.0, words / WORDS_PER_SECOND))
    after_first_15 = max(0.0, raw - 15)
    blocks = int((after_first_15 + NORMAL_SLOT_SECONDS - 1) // NORMAL_SLOT_SECONDS)
    return 15 + blocks * NORMAL_SLOT_SECONDS


def source_window(news_dir: Path, target_date: date) -> dict[str, Any]:
    expected = expected_news_dates(target_date)
    available: list[str] = []
    missing: list[str] = []

    for item_date in expected:
        path = news_dir / f"{item_date.isoformat()}.txt"
        if path.exists() and path.read_text(encoding="utf-8").strip():
            available.append(path.name)
        else:
            missing.append(item_date.isoformat())

    return {
        "expected_dates": [item.isoformat() for item in expected],
        "available_files": available,
        "missing_dates": missing,
    }


def score_block(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "approved": bool(payload.get("approved", False)),
        "score": payload.get("score"),
        "problems": payload.get("problems", []),
        "improvements": payload.get("improvements", []),
    }


def infer_status(
    build_outcome: str,
    sources: dict[str, Any],
    script_exists: bool,
    approved_for_multimedia: bool,
    multimedia_plan_exists: bool,
) -> str:
    if build_outcome.lower() not in {"success", "succeeded"}:
        return "error"
    if not sources["available_files"]:
        return "no_source_news"
    if script_exists and not approved_for_multimedia:
        return "script_not_approved"
    if approved_for_multimedia and multimedia_plan_exists:
        return "complete"
    if script_exists:
        return "script_created"
    return "incomplete"


def build_report(
    target_date: date,
    news_dir: Path,
    scripts_root: Path,
    multimedia_root: Path,
    build_outcome: str,
) -> dict[str, Any]:
    episode = target_date.isoformat()
    scripts_dir = scripts_root / episode
    multimedia_dir = multimedia_root / episode

    selected = read_json(scripts_dir / "selected_news.json", {})
    reviews = read_json(scripts_dir / "reviews.json", {})
    media_plan = read_json(multimedia_dir / "plan.json", {})
    manifest = read_json(multimedia_dir / "manifest.json", [])
    script = read_text(scripts_dir / "script.txt")

    selected_items = selected.get("items", []) if isinstance(selected, dict) else []
    duplicates = (
        selected.get("discarded_duplicates", []) if isinstance(selected, dict) else []
    )
    segments = media_plan.get("segments", []) if isinstance(media_plan, dict) else []
    media_segments = [s for s in segments if s.get("mode") == "media"]
    presenter_segments = [s for s in segments if s.get("mode") == "presenter"]
    fallback_assets = [
        item for item in manifest if item.get("provider") == "generated_fallback"
    ] if isinstance(manifest, list) else []

    editorial = reviews.get("editorial", {}) if isinstance(reviews, dict) else {}
    seo = reviews.get("seo_master", {}) if isinstance(reviews, dict) else {}
    attention = (
        reviews.get("youtube_attention_master", {}) if isinstance(reviews, dict) else {}
    )
    approved = bool(reviews.get("approved_for_multimedia", False)) if isinstance(reviews, dict) else False
    sources = source_window(news_dir, target_date)

    status = infer_status(
        build_outcome=build_outcome,
        sources=sources,
        script_exists=bool(script),
        approved_for_multimedia=approved,
        multimedia_plan_exists=bool(segments),
    )

    return {
        "schema_version": 1,
        "episode_date": episode,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "build_outcome": build_outcome,
        "source_window": sources,
        "configuration": {
            "openai_model": os.getenv("OPENAI_MODEL", "gpt-5.4-nano"),
            "script_quality_threshold": float(os.getenv("SCRIPT_QUALITY_THRESHOLD", "8.7")),
            "judge_threshold": float(os.getenv("JUDGE_THRESHOLD", "8.5")),
            "max_refinement_iterations": int(os.getenv("MAX_REFINEMENT_ITERATIONS", "5")),
            "max_selected_news": int(os.getenv("MAX_SELECTED_NEWS", "8")),
            "max_media_downloads": int(os.getenv("MAX_MEDIA_DOWNLOADS", "12")),
            "download_multimedia": os.getenv("DOWNLOAD_MULTIMEDIA", "true").strip().lower()
            not in {"0", "false", "no"},
            "selection_history_days": int(os.getenv("SELECTION_HISTORY_DAYS", "30")),
            "first_15_seconds_slot_size": FIRST_15_SLOT_SECONDS,
            "normal_slot_size": NORMAL_SLOT_SECONDS,
        },
        "selection": {
            "selected_count": len(selected_items),
            "selected_titles": [item.get("title", "") for item in selected_items],
            "discarded_duplicates_count": len(duplicates),
            "discarded_duplicates": duplicates,
        },
        "script": {
            "exists": bool(script),
            "path": str(scripts_dir / "script.txt"),
            "word_count": len(script.split()) if script else 0,
            "estimated_duration_seconds": estimate_duration_seconds(script),
            "approved_for_multimedia": approved,
        },
        "judges": {
            "editorial": {
                **score_block(editorial),
                "factuality_risk": editorial.get("factuality_risk"),
            },
            "seo_master": score_block(seo),
            "youtube_attention_master": score_block(attention),
        },
        "multimedia": {
            "plan_exists": bool(segments),
            "total_slots": len(segments),
            "media_slots": len(media_segments),
            "presenter_slots": len(presenter_segments),
            "downloaded_assets": len(manifest) if isinstance(manifest, list) else 0,
            "fallback_assets": len(fallback_assets),
            "plan_path": str(multimedia_dir / "plan.json"),
            "manifest_path": str(multimedia_dir / "manifest.json"),
        },
        "artifacts": {
            "selected_news": str(scripts_dir / "selected_news.json"),
            "reviews": str(scripts_dir / "reviews.json"),
            "script": str(scripts_dir / "script.txt"),
            "multimedia_plan": str(multimedia_dir / "plan.json"),
            "multimedia_manifest": str(multimedia_dir / "manifest.json"),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an episode run_report.json")
    parser.add_argument("--target-date", required=True, help="Episode date in YYYY-MM-DD")
    parser.add_argument("--build-outcome", default="success")
    parser.add_argument("--news-dir", default="news")
    parser.add_argument("--scripts-dir", default="scripts")
    parser.add_argument("--multimedia-dir", default="multimedia")
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
    )
    output_path = output_dir / "run_report.json"
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Run report created at {output_path}")
    print(json.dumps({"status": report["status"], "episode_date": report["episode_date"]}))


if __name__ == "__main__":
    main()
