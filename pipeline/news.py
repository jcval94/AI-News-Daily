from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field


_SOURCE_STEM_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})(?:-(?P<time>\d{2}-\d{2}-\d{2}))?$"
)


class NewsItem(BaseModel):
    news_id: str
    source_file: str
    source_locator: str
    item_index: int = Field(ge=1)
    title: str
    date: str
    date_origin: Literal["field", "source_file"]
    source: str
    url: str = ""
    url_quality: Literal["article", "generic", "missing"]
    category: str = ""
    summary: str = ""
    why_it_matters: str = ""
    raw_content: str


def classify_url(url: str) -> Literal["article", "generic", "missing"]:
    value = str(url or "").strip()
    if not value:
        return "missing"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "missing"
    path = parsed.path.rstrip("/").lower()
    generic_suffixes = (
        "",
        "/blog",
        "/news",
        "/announcements",
        "/blog-category/announcements",
        "/press",
        "/updates",
    )
    if path in generic_suffixes or "/blog-category/" in path:
        return "generic"
    return "article"


def source_date_from_path(path: Path) -> str:
    """Return the editorial date encoded in canonical or timestamped source filenames."""
    match = _SOURCE_STEM_RE.fullmatch(path.stem)
    return match.group("date") if match else ""


def resolve_news_file(news_dir: Path, news_date: date | str) -> Path | None:
    """Resolve one source file for an editorial day.

    Canonical ``YYYY-MM-DD.txt`` wins. If the producer emits timestamped files such as
    ``YYYY-MM-DD-HH-MM-SS.txt``, the latest non-empty timestamped file wins. This keeps
    production compatible with append-only daily ingestion while preserving a single
    deterministic source per editorial day.
    """
    value = news_date.isoformat() if isinstance(news_date, date) else str(news_date)
    canonical = news_dir / f"{value}.txt"
    if canonical.exists() and canonical.is_file() and canonical.read_text(encoding="utf-8").strip():
        return canonical

    candidates: list[Path] = []
    for path in news_dir.glob(f"{value}-*.txt"):
        if not path.is_file():
            continue
        match = _SOURCE_STEM_RE.fullmatch(path.stem)
        if not match or match.group("date") != value or not match.group("time"):
            continue
        if not path.read_text(encoding="utf-8").strip():
            continue
        candidates.append(path)
    return max(candidates, key=lambda item: item.name) if candidates else None


def _field(block: str, *labels: str) -> str:
    for label in labels:
        match = re.search(rf"(?mi)^{re.escape(label)}\s*:\s*(.+?)\s*$", block)
        if match:
            return match.group(1).strip()
    return ""


def _item_matches(text: str) -> list[re.Match[str]]:
    """Parse both canonical Markdown headings and the repository's older numbered format."""
    pattern = re.compile(r"(?m)^(?:##\s+)?(\d+)(?:\.|\))\s+(.+?)\s*$")
    return list(pattern.finditer(text))


def _title_matches(text: str) -> list[re.Match[str]]:
    """Parse current daily-digest blocks that start with ``Título: ...``."""
    return list(re.finditer(r"(?mi)^Título\s*:\s*(.+?)\s*$", text))


def _build_item(
    *,
    path: Path,
    item_index: int,
    title: str,
    block: str,
    file_date: str,
) -> NewsItem:
    explicit_date = _field(block, "Fecha")
    date_value = explicit_date or file_date
    if not date_value:
        raise ValueError(f"News item {item_index} in {path} has no date and filename has no editorial date")

    source = _field(block, "Fuente")
    if not source:
        raise ValueError(f"News item {item_index} in {path} has no Fuente field")

    url = _field(block, "Enlace")
    stable_source_id = file_date or path.stem
    source_file = path.name
    return NewsItem(
        news_id=f"{stable_source_id}:{item_index}",
        source_file=source_file,
        source_locator=f"{source_file}#item-{item_index}",
        item_index=item_index,
        title=title.strip(),
        date=date_value,
        date_origin="field" if explicit_date else "source_file",
        source=source,
        url=url,
        url_quality=classify_url(url),
        category=_field(block, "Categoría"),
        summary=_field(block, "Resumen", "Resumen breve"),
        why_it_matters=_field(block, "Por qué importa"),
        raw_content=block,
    )


def parse_news_file(path: Path) -> list[NewsItem]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    file_date = source_date_from_path(path)
    numbered = _item_matches(text)
    items: list[NewsItem] = []

    if numbered:
        seen_indices: set[int] = set()
        for position, match in enumerate(numbered):
            item_index = int(match.group(1))
            if item_index in seen_indices:
                raise ValueError(f"Duplicate news item index {item_index} in {path}")
            seen_indices.add(item_index)
            start = match.start()
            end = numbered[position + 1].start() if position + 1 < len(numbered) else len(text)
            block = text[start:end].strip()
            items.append(
                _build_item(
                    path=path,
                    item_index=item_index,
                    title=match.group(2),
                    block=block,
                    file_date=file_date,
                )
            )
        return items

    titled = _title_matches(text)
    if titled:
        for position, match in enumerate(titled):
            start = match.start()
            end = titled[position + 1].start() if position + 1 < len(titled) else len(text)
            block = text[start:end].strip()
            items.append(
                _build_item(
                    path=path,
                    item_index=position + 1,
                    title=match.group(1),
                    block=block,
                    file_date=file_date,
                )
            )
        return items

    raise ValueError(
        f"No structured news items found in {path}; expected numbered headings or blocks starting with 'Título:'"
    )
