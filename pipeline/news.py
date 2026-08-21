from __future__ import annotations

import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field


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


def _field(block: str, label: str) -> str:
    match = re.search(rf"(?mi)^{re.escape(label)}\s*:\s*(.+?)\s*$", block)
    return match.group(1).strip() if match else ""


def parse_news_file(path: Path) -> list[NewsItem]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    matches = list(re.finditer(r"(?m)^##\s+(\d+)\.\s+(.+?)\s*$", text))
    if not matches:
        raise ValueError(f"No structured '## N. title' news items found in {path}")

    file_date = path.stem if re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.stem) else ""
    items: list[NewsItem] = []
    for position, match in enumerate(matches):
        item_index = int(match.group(1))
        start = match.start()
        end = matches[position + 1].start() if position + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        title = match.group(2).strip()
        explicit_date = _field(block, "Fecha")
        date_value = explicit_date or file_date
        date_origin: Literal["field", "source_file"] = "field" if explicit_date else "source_file"
        url = _field(block, "Enlace")
        source_file = path.name
        items.append(
            NewsItem(
                news_id=f"{path.stem}:{item_index}",
                source_file=source_file,
                source_locator=f"{source_file}#item-{item_index}",
                item_index=item_index,
                title=title,
                date=date_value,
                date_origin=date_origin,
                source=_field(block, "Fuente"),
                url=url,
                url_quality=classify_url(url),
                category=_field(block, "Categoría"),
                summary=_field(block, "Resumen"),
                why_it_matters=_field(block, "Por qué importa"),
                raw_content=block,
            )
        )
    return items
