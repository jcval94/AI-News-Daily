from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pipeline.core import expected_news_dates
from pipeline.news import NewsItem
from pipeline.news_resolution import candidate_news_files, load_news_for_date
from pipeline.source_naming import is_supported_source, source_date


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _source_quality(items: list[NewsItem], *, parseable_days: int, expected_days: int) -> dict[str, Any]:
    """Observational source-quality telemetry. It never changes production gating."""
    item_count = len(items)
    article_urls = sum(1 for item in items if item.url_quality == "article")
    complete_metadata = sum(
        1
        for item in items
        if item.title.strip()
        and item.source.strip()
        and item.date.strip()
        and item.summary.strip()
        and item.why_it_matters.strip()
    )
    source_names = [item.source.strip().casefold() for item in items if item.source.strip()]
    domains = []
    for item in items:
        try:
            host = urlparse(item.url).netloc.casefold().split(":")[0]
        except ValueError:
            host = ""
        if host:
            domains.append(host.removeprefix("www."))

    unique_sources = len(set(source_names))
    unique_domains = len(set(domains))
    parseable_day_ratio = _ratio(parseable_days, expected_days)
    article_url_ratio = _ratio(article_urls, item_count)
    metadata_completeness_ratio = _ratio(complete_metadata, item_count)
    source_diversity_ratio = round(min(1.0, unique_sources / 3), 4) if items else 0.0
    domain_diversity_ratio = round(min(1.0, unique_domains / 3), 4) if items else 0.0

    score = round(
        100
        * (
            0.25 * parseable_day_ratio
            + 0.25 * article_url_ratio
            + 0.20 * metadata_completeness_ratio
            + 0.15 * source_diversity_ratio
            + 0.15 * domain_diversity_ratio
        ),
        1,
    )
    band = "high" if score >= 80 else "medium" if score >= 60 else "low"
    return {
        "score": score,
        "band": band,
        "observational_only": True,
        "parseable_day_ratio": parseable_day_ratio,
        "article_url_ratio": article_url_ratio,
        "metadata_completeness_ratio": metadata_completeness_ratio,
        "source_diversity_ratio": source_diversity_ratio,
        "domain_diversity_ratio": domain_diversity_ratio,
        "unique_source_count": unique_sources,
        "unique_domain_count": unique_domains,
        "article_url_count": article_urls,
        "complete_metadata_count": complete_metadata,
        "source_counts": dict(sorted(Counter(source_names).items())),
        "domain_counts": dict(sorted(Counter(domains).items())),
    }


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
    unparseable_dates: list[str] = []
    parsed_items: list[NewsItem] = []
    source_resolution: list[dict[str, Any]] = []
    duplicate_source_dates: list[str] = []

    for current in expected:
        candidates = candidate_news_files(news_dir, current)
        path, parsed = load_news_for_date(news_dir, current)
        candidate_names = [candidate.name for candidate in candidates]
        if len(candidate_names) > 1:
            duplicate_source_dates.append(current.isoformat())

        if path is None:
            if candidate_names:
                unparseable_dates.append(current.isoformat())
                resolution_status = "unparseable"
            else:
                missing_dates.append(current.isoformat())
                resolution_status = "missing"
        else:
            available_files.append(path.name)
            parsed_items.extend(parsed)
            resolution_status = "parseable"

        source_resolution.append(
            {
                "date": current.isoformat(),
                "status": resolution_status,
                "selected_file": path.name if path is not None else None,
                "candidate_files": candidate_names,
                "candidate_count": len(candidate_names),
                "parsed_item_count": len(parsed),
            }
        )

    detected_repository_dates = []
    parseable_repository_dates = []
    if news_dir.exists():
        by_date: set[Any] = set()
        for source in news_dir.iterdir():
            if not is_supported_source(source):
                continue
            value = source_date(source)
            if value is not None:
                detected_repository_dates.append(value)
                by_date.add(value)
        for value in sorted(by_date):
            path, parsed = load_news_for_date(news_dir, value)
            if path is not None and parsed:
                parseable_repository_dates.append(value)

    latest_detected_source_date = (
        max(detected_repository_dates) if detected_repository_dates else None
    )
    latest_parseable_source_date = (
        max(parseable_repository_dates) if parseable_repository_dates else None
    )
    source_staleness_days = (
        max(0, (target - latest_parseable_source_date).days)
        if latest_parseable_source_date is not None
        else None
    )

    expected_count = len(expected)
    available_count = len(available_files)
    ratio = available_count / expected_count if expected_count else 0.0
    item_count = len(parsed_items)
    sufficient = ratio >= min_ratio and item_count > 0
    quality = _source_quality(
        parsed_items,
        parseable_days=available_count,
        expected_days=expected_count,
    )
    return {
        "schema_version": 2,
        "episode_date": target_date,
        "source_mode": os.getenv("NEWS_SOURCE_MODE", "scheduled_window"),
        "expected_dates": [value.isoformat() for value in expected],
        "available_files": available_files,
        "parseable_dates": [
            row["date"] for row in source_resolution if row["status"] == "parseable"
        ],
        "missing_dates": missing_dates,
        "unparseable_dates": unparseable_dates,
        "source_resolution": source_resolution,
        "duplicate_source_dates": duplicate_source_dates,
        "duplicate_source_day_count": len(duplicate_source_dates),
        "latest_repository_source_date": (
            latest_detected_source_date.isoformat()
            if latest_detected_source_date is not None
            else None
        ),
        "latest_detected_source_date": (
            latest_detected_source_date.isoformat()
            if latest_detected_source_date is not None
            else None
        ),
        "latest_parseable_source_date": (
            latest_parseable_source_date.isoformat()
            if latest_parseable_source_date is not None
            else None
        ),
        "source_staleness_basis": "latest_parseable_source",
        "source_staleness_days": source_staleness_days,
        "expected_day_count": expected_count,
        "available_day_count": available_count,
        "coverage_ratio": round(ratio, 4),
        "minimum_coverage_ratio": min_ratio,
        "item_count": item_count,
        "source_quality": quality,
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
                f"Insufficient parseable source coverage: {available}/{expected} editorial days "
                f"({ratio:.0%}) below required {threshold:.0%}"
            ),
            "started_at_utc": payload.get("checked_at_utc"),
            "finished_at_utc": _utc_now(),
            "refinement_iterations": 0,
            "validation_warnings": [
                f"Missing source dates: {', '.join(payload.get('missing_dates', [])) or 'none'}",
                (
                    "Unparseable source dates: "
                    f"{', '.join(payload.get('unparseable_dates', [])) or 'none'}"
                ),
                (
                    "Duplicate source dates: "
                    f"{', '.join(payload.get('duplicate_source_dates', [])) or 'none'}"
                ),
                (
                    "Latest parseable repository source: "
                    f"{payload.get('latest_parseable_source_date') or 'none'} "
                    f"(staleness_days={payload.get('source_staleness_days')})"
                ),
            ],
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate parseable editorial source-window coverage before model calls")
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
