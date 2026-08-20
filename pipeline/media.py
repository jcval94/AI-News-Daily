from __future__ import annotations

import html
import io
import os
import re
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

USER_AGENT = "AI-News-Daily/1.0 (GitHub Actions; educational video pipeline)"


def _safe_text(value: Any) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", "", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()


def _download_bytes(url: str) -> bytes:
    response = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.content


def _save_as_jpeg(data: bytes, destination: Path) -> None:
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGB")
        image = ImageOps.fit(image, (1280, 720), method=Image.Resampling.LANCZOS)
        image.save(destination, "JPEG", quality=88, optimize=True)


def search_pexels(query: str) -> dict[str, Any] | None:
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        return None
    response = requests.get(
        "https://api.pexels.com/v1/search",
        params={"query": query, "per_page": 5, "orientation": "landscape"},
        headers={"Authorization": api_key, "User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    photos = response.json().get("photos", [])
    if not photos:
        return None
    photo = photos[0]
    return {
        "provider": "pexels",
        "download_url": photo["src"].get("large2x") or photo["src"]["large"],
        "source_url": photo.get("url", ""),
        "creator": photo.get("photographer", ""),
        "license": "Pexels License",
    }


def search_wikimedia(query: str) -> dict[str, Any] | None:
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap",
        "gsrnamespace": 6,
        "gsrlimit": 8,
        "prop": "imageinfo",
        "iiprop": "url|mime|extmetadata",
        "iiurlwidth": 1600,
        "format": "json",
        "formatversion": 2,
    }
    response = requests.get(
        "https://commons.wikimedia.org/w/api.php",
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", [])
    for page in pages:
        info_list = page.get("imageinfo") or []
        if not info_list:
            continue
        info = info_list[0]
        mime = info.get("mime", "")
        if mime not in {"image/jpeg", "image/png", "image/webp"}:
            continue
        meta = info.get("extmetadata", {})
        return {
            "provider": "wikimedia_commons",
            "download_url": info.get("thumburl") or info.get("url"),
            "source_url": info.get("descriptionurl") or info.get("url", ""),
            "creator": _safe_text(meta.get("Artist", {}).get("value", "")),
            "license": _safe_text(
                meta.get("LicenseShortName", {}).get("value", "")
                or meta.get("UsageTerms", {}).get("value", "")
            ),
            "title": page.get("title", ""),
        }
    return None


def make_fallback_card(text: str, destination: Path) -> None:
    image = Image.new("RGB", (1280, 720), "#10131a")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=42)
    small = ImageFont.load_default(size=24)
    clean = text.strip()[:120]
    words = clean.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join(current + [word])
        if len(candidate) > 34 and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    y = 250
    for line in lines[:4]:
        draw.text((90, y), line, fill="white", font=font)
        y += 58
    draw.text((90, 620), "AI NEWS DAILY • fallback visual", fill="#b9c1d0", font=small)
    image.save(destination, "JPEG", quality=90)


def download_shot_asset(shot: dict[str, Any], destination: Path) -> dict[str, Any]:
    query = shot["visual_query"]
    record: dict[str, Any] | None = None
    errors: list[str] = []

    for provider in (search_pexels, search_wikimedia):
        try:
            record = provider(query)
            if record:
                data = _download_bytes(record["download_url"])
                _save_as_jpeg(data, destination)
                break
        except Exception as exc:  # network/provider failures should not kill the whole kit
            errors.append(f"{provider.__name__}: {exc}")
            record = None

    if not record:
        make_fallback_card(shot.get("on_screen_text") or query, destination)
        record = {
            "provider": "generated_fallback",
            "source_url": "",
            "creator": "AI-News-Daily",
            "license": "Generated locally",
        }

    return {
        "shot_number": shot["shot_number"],
        "visual_query": query,
        "file": str(destination),
        "provider": record.get("provider", ""),
        "source_url": record.get("source_url", ""),
        "creator": record.get("creator", ""),
        "license": record.get("license", ""),
        "errors": errors,
    }
