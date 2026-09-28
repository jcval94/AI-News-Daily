from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pipeline.news import parse_news_file
from pipeline.source_naming import files_for_date

TZ = ZoneInfo("America/Mexico_City")


def evaluate_daily_ingestion(
    *,
    day: date,
    news_dir: Path,
    minimum_items: int = 5,
) -> dict[str, Any]:
    candidates = files_for_date(news_dir, day)
    inspected: list[dict[str, Any]] = []
    selected: Path | None = None
    selected_count = 0

    for path in candidates:
        try:
            items = parse_news_file(path)
            error = ""
        except (OSError, UnicodeError, ValueError) as exc:
            items = []
            error = str(exc)[:500]
        count = len(items)
        inspected.append(
            {
                "file": path.name,
                "item_count": count,
                "parseable": bool(items),
                "error": error,
            }
        )
        if selected is None and count >= minimum_items:
            selected = path
            selected_count = count

    if selected is not None:
        status = "ok"
        reason = f"Daily digest is present and parseable with {selected_count} items."
    elif not candidates:
        status = "missing"
        reason = "No news digest exists for the local calendar day."
    elif any(item["parseable"] for item in inspected):
        status = "thin"
        reason = f"Digest exists but has fewer than {minimum_items} parseable items."
    else:
        status = "invalid"
        reason = "Digest candidates exist but none can be parsed."

    return {
        "schema_version": 1,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "date": day.isoformat(),
        "status": status,
        "healthy": status == "ok",
        "minimum_items": minimum_items,
        "selected_file": selected.name if selected is not None else None,
        "item_count": selected_count,
        "candidate_count": len(candidates),
        "candidates": inspected,
        "reason": reason,
    }


def _write_output(name: str, value: str) -> None:
    path = os.getenv("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify that today's AI News digest arrived")
    parser.add_argument("--date", default="")
    parser.add_argument("--news-dir", default="news")
    parser.add_argument("--minimum-items", type=int, default=5)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    day = date.fromisoformat(args.date) if args.date else datetime.now(TZ).date()
    report = evaluate_daily_ingestion(
        day=day,
        news_dir=Path(args.news_dir),
        minimum_items=args.minimum_items,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    _write_output("date", str(report["date"]))
    _write_output("status", str(report["status"]))
    _write_output("healthy", "true" if report["healthy"] else "false")
    _write_output("selected_file", str(report["selected_file"] or ""))
    if not report["healthy"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
