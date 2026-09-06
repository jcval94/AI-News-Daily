from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from pipeline.core import expected_news_dates
from pipeline.news import NewsItem, parse_news_file

_TIMESTAMPED_NAME = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})-\d{2}-\d{2}-\d{2}\.txt$")


def candidate_news_files(news_dir: Path, news_date: date) -> list[Path]:
    """Return supported source files for one editorial day, newest first.

    Timestamped files are preferred because they are collision-safe and can represent
    multiple captures in one day. The legacy YYYY-MM-DD.txt form remains a fallback.
    """
    day = news_date.isoformat()
    timestamped = sorted(
        (
            path
            for path in news_dir.glob(f"{day}-*.txt")
            if (match := _TIMESTAMPED_NAME.fullmatch(path.name))
            and match.group("date") == day
        ),
        key=lambda path: path.name,
        reverse=True,
    )
    legacy = news_dir / f"{day}.txt"
    if legacy.exists():
        timestamped.append(legacy)
    return timestamped


def load_news_for_date(news_dir: Path, news_date: date) -> tuple[Path | None, list[NewsItem]]:
    """Load the newest usable source for a day, falling back when necessary."""
    for path in candidate_news_files(news_dir, news_date):
        try:
            if not path.read_text(encoding="utf-8").strip():
                continue
            items = parse_news_file(path)
        except (OSError, UnicodeError, ValueError):
            continue
        if items:
            return path, items
    return None, []


def collect_available_news(
    news_dir: Path,
    target_date: date,
) -> tuple[str, list[Path], list[date], list[NewsItem]]:
    """Collect the configured editorial window using both supported filename formats."""
    available: list[Path] = []
    missing: list[date] = []
    items: list[NewsItem] = []
    for news_date in expected_news_dates(target_date):
        path, parsed = load_news_for_date(news_dir, news_date)
        if path is None:
            missing.append(news_date)
            continue
        available.append(path)
        items.extend(parsed)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "items": [item.model_dump() for item in items],
    }
    return json.dumps(payload, ensure_ascii=False), available, missing, items


def install(base: Any) -> Any:
    """Install the shared resolver into the legacy pipeline.run module."""
    base.collect_available_news = collect_available_news
    return base
