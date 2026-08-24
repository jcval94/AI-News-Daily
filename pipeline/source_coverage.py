from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.core import expected_news_dates
from pipeline.news import parse_news_file


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def evaluate_source_coverage(
    *,
    target_date: str,
    news_dir: Path,
    min_ratio: float,
) -> dict[str, Any]:
    target = datetime.strptime(target_date, "%Y-%m-%d").date()
    expected = expected_news_dates(target)
    available_files: list[str] = []
    missing_dates: list[str] = []
    item_count = 0

    for current in expected:
        path = news_dir / f"{current.isoformat()}.txt"
        if not path.exists() or not path.read_text(encoding="utf-8").strip():
            missing_dates.append(current.isoformat())
            continue
        parsed = parse_news_file(path)
        if not parsed:
            missing_dates.append(current.isoformat())
            continue
        available_files.append(path.name)
        item_count += len(parsed)

    expected_count = len(expected)
    available_count = len(available_files)
    ratio = available_count / expected_count if expected_count else 0.0
    sufficient = ratio >= min_ratio and item_count > 0
    return {
        "schema_version": 1,
        "episode_date": target_date,
        "source_mode": os.getenv("NEWS_SOURCE_MODE", "scheduled_window"),
        "expected_dates": [value.isoformat() for value in expected],
        "available_files": available_files,
        "missing_dates": missing_dates,
        "expected_day_count": expected_count,
        "available_day_count": available_count,
        "coverage_ratio": round(ratio, 4),
        "minimum_coverage_ratio": min_ratio,
        "item_count": item_count,
        "sufficient": sufficient,
        "checked_at_utc": _utc_now(),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_skip_state(path: Path, payload: dict[str, Any]) -> None:
    available = int(payload.get("available_day_count", 0) or 0)
    expected = int(payload.get("expected_day_count", 0) or 0)
    ratio = float(payload.get("coverage_ratio", 0) or 0)
    threshold = float(payload.get("minimum_coverage_ratio", 0) or 0)
    _write_json(
        path,
        {
            "schema_version": 1,
            "episode_date": payload.get("episode_date"),
            "status": "no_source_news",
            "publishable": False,
            "reason": (
                f"Insufficient source coverage: {available}/{expected} editorial days "
                f"({ratio:.0%}) below required {threshold:.0%}"
            ),
            "started_at_utc": payload.get("checked_at_utc"),
            "finished_at_utc": _utc_now(),
            "refinement_iterations": 0,
            "validation_warnings": [
                f"Missing source dates: {', '.join(payload.get('missing_dates', [])) or 'none'}"
            ],
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate editorial source-window coverage before model calls")
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--news-dir", default="news")
    parser.add_argument("--output", required=True)
    parser.add_argument("--state-out", default="")
    parser.add_argument(
        "--min-ratio",
        type=float,
        default=float(os.getenv("MIN_SOURCE_COVERAGE_RATIO", "0.75")),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not (0 < args.min_ratio <= 1):
        raise SystemExit("MIN_SOURCE_COVERAGE_RATIO must be > 0 and <= 1")
    payload = evaluate_source_coverage(
        target_date=args.target_date,
        news_dir=Path(args.news_dir),
        min_ratio=args.min_ratio,
    )
    _write_json(Path(args.output), payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["sufficient"]:
        if args.state_out:
            write_skip_state(Path(args.state_out), payload)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
