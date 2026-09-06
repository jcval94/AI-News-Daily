from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from pipeline.core import expected_news_dates
from pipeline.news import NewsItem, parse_news_file
from pipeline.source_naming import files_for_date


def candidate_news_files(news_dir: Path, news_date: date) -> list[Path]:
    """Return every supported source file for one editorial day, newest first.

    Discovery is semantic rather than tied to one producer filename. A source may
    encode the date anywhere in its .txt filename (with optional embedded time) or,
    when the filename is arbitrary, through an unambiguous repeated ``Fecha:`` value
    in the file content. Timestamped captures are preferred deterministically.
    """
    return files_for_date(news_dir, news_date)


def load_news_for_date(news_dir: Path, news_date: date) -> tuple[Path | None, list[NewsItem]]:
    """Load the newest usable source for a day, falling back across naming variants."""
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
    """Collect the configured editorial window across all supported source names."""
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
