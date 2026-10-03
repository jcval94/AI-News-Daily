from __future__ import annotations

import argparse
import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from pipeline.news import classify_url
from pipeline.news_resolution import load_news_for_date
from pipeline.runtime_hardening import is_permanent_quota_error
from pipeline.source_coverage import evaluate_source_coverage

TZ = ZoneInfo("America/Mexico_City")
SCHEDULED_WEEKDAYS = {1, 4}  # Tuesday / Friday


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def next_scheduled_date(as_of: date) -> date:
    for offset in range(0, 8):
        candidate = as_of + timedelta(days=offset)
        if candidate.weekday() in SCHEDULED_WEEKDAYS:
            return candidate
    raise RuntimeError("Could not resolve next scheduled production date")


def evaluate_source_quality(
    coverage: dict[str, Any],
    news_dir: Path,
    *,
    min_items_per_day: int = 5,
    min_concrete_url_ratio: float = 0.8,
) -> dict[str, Any]:
    days: list[dict[str, Any]] = []
    for raw_day in coverage.get("expected_dates", []):
        current = date.fromisoformat(str(raw_day))
        path, items = load_news_for_date(news_dir, current)
        if path is None:
            continue
        concrete = sum(1 for item in items if classify_url(str(item.url or "")) == "article")
        count = len(items)
        concrete_ratio = concrete / count if count else 0.0
        days.append(
            {
                "date": current.isoformat(),
                "file": path.name,
                "item_count": count,
                "concrete_url_ratio": round(concrete_ratio, 4),
                "sufficient": count >= min_items_per_day and concrete_ratio >= min_concrete_url_ratio,
            }
        )

    sufficient = bool(days) and all(day["sufficient"] for day in days)
    return {
        "minimum_items_per_available_day": min_items_per_day,
        "minimum_concrete_url_ratio": min_concrete_url_ratio,
        "available_day_count": len(days),
        "sufficient": sufficient,
        "days": days,
    }


def classify_model_error(exc: Exception) -> str:
    if is_permanent_quota_error(exc):
        return "permanent_quota"
    parts = [str(exc)]
    for attr in ("code", "type", "message"):
        value = getattr(exc, attr, None)
        if value:
            parts.append(str(value))
    haystack = " ".join(parts).casefold()
    if any(marker in haystack for marker in ("invalid_api_key", "incorrect api key", "authentication", "401")):
        return "authentication"
    if any(marker in haystack for marker in ("model_not_found", "model does not exist", "404")):
        return "model_unavailable"
    if "rate limit" in haystack or "429" in haystack:
        return "transient_rate_limit"
    return "model_error"


def probe_openai_model(model: str, api_key: str) -> dict[str, Any]:
    if not api_key.strip():
        return {
            "available": False,
            "status": "missing_secret",
            "model": model,
            "elapsed_seconds": 0.0,
            "error": "OPENAI_API_KEY is not configured.",
        }

    started = time.monotonic()
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, timeout=30.0, max_retries=0)
        response = client.responses.create(
            model=model,
            input="Reply with exactly OK.",
            max_output_tokens=16,
        )
        return {
            "available": True,
            "status": "ok",
            "model": model,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "response_id": str(getattr(response, "id", "") or ""),
        }
    except Exception as exc:
        return {
            "available": False,
            "status": classify_model_error(exc),
            "model": model,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
        }


def run_preflight(
    *,
    as_of: date,
    target_date: date | None,
    news_dir: Path,
    min_ratio: float,
    model: str,
    api_key: str,
    probe_fn: Callable[[str, str], dict[str, Any]] = probe_openai_model,
) -> dict[str, Any]:
    target = target_date or next_scheduled_date(as_of)
    coverage = evaluate_source_coverage(
        target_date=target.isoformat(),
        news_dir=news_dir,
        min_ratio=min_ratio,
    )
    source_quality = evaluate_source_quality(coverage, news_dir)
    model_probe = probe_fn(model, api_key)

    blockers: list[str] = []
    if not coverage.get("sufficient"):
        blockers.append("source_coverage")
    if coverage.get("sufficient") and not source_quality.get("sufficient"):
        blockers.append("source_quality")
    if not model_probe.get("available"):
        blockers.append(f"model_probe:{model_probe.get('status', 'unknown')}")

    pending_dates = [
        str(raw_day) for raw_day in coverage.get("missing_dates", [])
        if date.fromisoformat(str(raw_day)) > as_of
    ]
    pending = (
        bool(pending_dates)
        and blockers == ["source_coverage"]
        and source_quality.get("sufficient", False)
    )

    return {
        "schema_version": 1,
        "checked_at_utc": _utc_now(),
        "as_of_date": as_of.isoformat(),
        "target_date": target.isoformat(),
        "ready": not blockers,
        "pending": pending,
        "pending_source_dates": pending_dates,
        "blockers": blockers,
        "source_coverage": coverage,
        "source_quality": source_quality,
        "model_probe": model_probe,
    }


def _write_output(name: str, value: str) -> None:
    path = os.getenv("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cheap readiness gate before scheduled AI News production")
    parser.add_argument("--target-date", default="")
    parser.add_argument("--as-of", default="")
    parser.add_argument("--news-dir", default="news")
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
        raise SystemExit("MIN_SOURCE_COVERAGE_RATIO must be > 0 and <= 1")

    as_of = (
        date.fromisoformat(args.as_of)
        if args.as_of
        else datetime.now(TZ).date()
    )
    target = date.fromisoformat(args.target_date) if args.target_date else None
    report = run_preflight(
        as_of=as_of,
        target_date=target,
        news_dir=Path(args.news_dir),
        min_ratio=args.min_ratio,
        model=os.getenv("OPENAI_MODEL", "gpt-5.4-nano"),
        api_key=os.getenv("OPENAI_API_KEY", ""),
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    _write_output("target_date", str(report["target_date"]))
    _write_output("ready", "true" if report["ready"] else "false")
    _write_output("pending", "true" if report["pending"] else "false")
    _write_output("model_status", str(report["model_probe"].get("status") or "unknown"))
    if not report["ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
