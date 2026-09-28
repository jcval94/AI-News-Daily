from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pipeline.narrative_memory import load_memory
from pipeline.source_coverage import evaluate_source_coverage

MEXICO_CITY = ZoneInfo("America/Mexico_City")


def next_scheduled_production_date(as_of: date) -> date:
    for offset in range(0, 8):
        candidate = as_of + timedelta(days=offset)
        if candidate.weekday() in {1, 4}:  # Tuesday / Friday
            return candidate
    raise RuntimeError("Could not resolve next scheduled production date")


def _check(
    check_id: str,
    status: str,
    title: str,
    detail: str,
    *,
    value: Any = None,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status,
        "title": title,
        "detail": detail,
        "value": value,
    }


def build_preflight(
    *,
    repo_root: Path,
    target_date: date,
    min_ratio: float = 0.75,
    openai_configured: bool | None = None,
    pexels_configured: bool | None = None,
    youtube_configured: bool | None = None,
) -> dict[str, Any]:
    """Build a cheap, read-only production forecast for the next scheduled episode.

    This function never writes production state, consumes Narrative Memory, calls a
    model/provider, or promotes artifacts. The CLI may persist only its own report.
    """
    if openai_configured is None:
        openai_configured = bool(os.getenv("OPENAI_API_KEY", "").strip())
    if pexels_configured is None:
        pexels_configured = bool(os.getenv("PEXELS_API_KEY", "").strip())
    if youtube_configured is None:
        youtube_configured = bool(os.getenv("YOUTUBE_API_KEY", "").strip())

    coverage = evaluate_source_coverage(
        target_date=target_date.isoformat(),
        news_dir=repo_root / "news",
        min_ratio=min_ratio,
    )
    quality = coverage.get("source_quality", {})
    memory_items, memory_issues = load_memory(repo_root / "editorial" / "narrative_memory.jsonl")

    coverage_ok = bool(coverage.get("sufficient"))
    memory_ok = bool(memory_items)
    required_secret_ok = bool(openai_configured)

    coverage_ratio = float(coverage.get("coverage_ratio", 0.0) or 0.0)
    quality_score = float(quality.get("score", 0.0) or 0.0)
    readiness_score = round(
        min(1.0, coverage_ratio) * 50
        + (quality_score / 100.0) * 25
        + (15 if memory_ok else 0)
        + (10 if required_secret_ok else 0),
        1,
    )
    hard_ready = coverage_ok and memory_ok and required_secret_ok
    status = "ready" if hard_ready else "at_risk"

    checks = [
        _check(
            "parseable-source-coverage",
            "pass" if coverage_ok else "fail",
            "Parseable source coverage",
            (
                f"{coverage.get('available_day_count', 0)}/{coverage.get('expected_day_count', 0)} "
                f"days parseable; minimum {min_ratio:.0%}."
            ),
            value=coverage_ratio,
        ),
        _check(
            "source-quality",
            "info",
            "Next-window source quality",
            "Observational only; it does not block production.",
            value=quality_score,
        ),
        _check(
            "narrative-memory",
            "pass" if memory_ok else "fail",
            "Narrative Memory",
            (
                f"{len(memory_items)} valid gated record(s); "
                f"{len(memory_issues)} quarantined/warning issue(s)."
            ),
            value=len(memory_items),
        ),
        _check(
            "openai-secret",
            "pass" if required_secret_ok else "fail",
            "Required model credential",
            "OPENAI_API_KEY is configured." if required_secret_ok else "OPENAI_API_KEY is missing.",
            value=required_secret_ok,
        ),
        _check(
            "optional-media-credentials",
            "info",
            "Optional media credentials",
            "Optional providers may improve media discovery but do not determine script readiness.",
            value={
                "pexels": bool(pexels_configured),
                "youtube": bool(youtube_configured),
            },
        ),
    ]

    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generated_local_date": datetime.now(MEXICO_CITY).date().isoformat(),
        "target_date": target_date.isoformat(),
        "status": status,
        "readiness_score": readiness_score,
        "side_effect_free": True,
        "model_calls": 0,
        "production_state_writes": 0,
        "memory_usage_writes": 0,
        "hard_requirements": {
            "parseable_source_coverage": coverage_ok,
            "narrative_memory_available": memory_ok,
            "openai_configured": required_secret_ok,
        },
        "checks": checks,
        "source_coverage": coverage,
        "source_quality": quality,
        "narrative_memory": {
            "valid_item_count": len(memory_items),
            "issues": memory_issues,
        },
        "credentials": {
            "openai_configured": bool(openai_configured),
            "pexels_configured": bool(pexels_configured),
            "youtube_configured": bool(youtube_configured),
        },
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a cheap read-only production preflight")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--target-date", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--min-ratio",
        type=float,
        default=float(os.getenv("MIN_SOURCE_COVERAGE_RATIO", "0.75")),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not (0 < args.min_ratio <= 1):
        raise SystemExit("--min-ratio must be > 0 and <= 1")
    local_today = datetime.now(MEXICO_CITY).date()
    target = (
        date.fromisoformat(args.target_date)
        if args.target_date
        else next_scheduled_production_date(local_today)
    )
    report = build_preflight(
        repo_root=Path(args.repo_root),
        target_date=target,
        min_ratio=args.min_ratio,
    )
    _write_json(Path(args.output), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
