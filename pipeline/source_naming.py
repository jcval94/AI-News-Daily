from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path


# Source discovery is intentionally based on semantics (embedded date / content date),
# not on one exact producer filename. Keep this module independent from pipeline.news
# so both parsing and discovery can reuse it without circular imports.
_DATE_RE = re.compile(
    r"(?<!\d)(?P<year>\d{4})[-_.](?P<month>\d{2})[-_.](?P<day>\d{2})(?!\d)"
)
_TIMESTAMP_RE = re.compile(
    r"(?<!\d)(?P<year>\d{4})[-_.](?P<month>\d{2})[-_.](?P<day>\d{2})"
    r"(?:[Tt _.-]+)"
    r"(?P<hour>[01]\d|2[0-3])[-_.:]"
    r"(?P<minute>[0-5]\d)"
    r"(?:[-_.:](?P<second>[0-5]\d))?(?!\d)"
)
_CONTENT_DATE_RE = re.compile(r"(?mi)^\s*Fecha\s*:\s*(\d{4}-\d{2}-\d{2})\s*$")


def _validated_date(year: str, month: str, day: str) -> date | None:
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def filename_date(path: Path) -> date | None:
    """Extract one valid calendar date from anywhere in a source filename.

    Examples accepted include:
    - 2026-09-05.txt
    - 2026-09-05-08-30-00.txt
    - ai-news_2026-09-05_08-30-00_capture.txt
    - daily.2026.09.05.final.TXT
    """
    name = path.stem
    for match in _DATE_RE.finditer(name):
        value = _validated_date(match.group("year"), match.group("month"), match.group("day"))
        if value is not None:
            return value
    return None


def filename_timestamp(path: Path) -> datetime | None:
    """Return an embedded timestamp when present, for deterministic newest-first ordering."""
    name = path.stem
    for match in _TIMESTAMP_RE.finditer(name):
        try:
            return datetime(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
                int(match.group("hour")),
                int(match.group("minute")),
                int(match.group("second") or 0),
            )
        except ValueError:
            continue
    return None


def content_date(path: Path) -> date | None:
    """Infer a day from repeated Fecha fields only when they agree.

    This lets producers use arbitrary filenames while failing closed for files that
    accidentally mix multiple editorial days.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    values: set[date] = set()
    for raw in _CONTENT_DATE_RE.findall(text):
        try:
            values.add(datetime.strptime(raw, "%Y-%m-%d").date())
        except ValueError:
            continue
    return next(iter(values)) if len(values) == 1 else None


def source_date(path: Path) -> date | None:
    """Resolve a source day without depending on an exact filename contract."""
    return filename_date(path) or content_date(path)


def is_supported_source(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".txt"


def source_sort_key(path: Path) -> tuple[int, datetime, str]:
    """Sort timestamped captures ahead of untimestamped sources, newest first."""
    stamp = filename_timestamp(path)
    return (
        1 if stamp is not None else 0,
        stamp or datetime.min,
        path.name.casefold(),
    )


def files_for_date(news_dir: Path, news_date: date) -> list[Path]:
    if not news_dir.exists():
        return []
    candidates = [
        path
        for path in news_dir.iterdir()
        if is_supported_source(path) and source_date(path) == news_date
    ]
    return sorted(candidates, key=source_sort_key, reverse=True)
