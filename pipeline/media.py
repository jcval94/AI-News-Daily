from __future__ import annotations

import html
import io
import os
import re
import time
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

from pipeline.core import PipelineConfig
from pipeline.licenses import assess_license

CONFIG = PipelineConfig.from_env()
USER_AGENT = "AI-News-Daily/1.0 (GitHub Actions; educational video pipeline)"
RETRYABLE_HTTP_STATUS = {408, 409, 429, 500, 502, 503, 504}
_MEDIA_STOPWORDS = {
    "a", "an", "and", "the", "of", "for", "in", "on", "with", "to", "ai", "artificial",
    "intelligence", "image", "photo", "visual", "concept", "illustration", "technology",
}
_DECORATIVE_CLICHES = {
    "scrabble", "wooden", "letters", "tiles", "word", "alphabet", "sticky", "handshake",
    "businessman", "businesswoman", "generic", "stock",
}
_TOKEN_ALIASES = {
    "cybersecurity": ("cyber", "security"),
    "supercomputer": ("super", "computer"),
    "supercomputing": ("super", "computing"),
    "workflow": ("work", "flow"),
}


def _safe_text(value: Any) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", "", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()


def _semantic_tokens(value: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", _safe_text(value).lower())
    expanded: list[str] = []
    for word in words:
        expanded.extend(_TOKEN_ALIASES.get(word, (word,)))
    return {word[:7] for word in expanded if len(word) > 2 and word not in _MEDIA_STOPWORDS}


def media_relevance_score(query: str, candidate_text: str) -> float:
    query_tokens = _semantic_tokens(query)
    candidate_tokens = _semantic_tokens(candidate_text)
    if not query_tokens or not candidate_tokens:
        return 0.0
    shared = query_tokens & candidate_tokens
    coverage = len(shared) / len(query_tokens)
    jaccard = len(shared) / len(query_tokens | candidate_tokens)
    score = (0.82 * coverage) + (0.18 * jaccard)
    candidate_words = set(re.findall(r"[a-z0-9]+", _safe_text(candidate_text).lower()))
    if candidate_words & _DECORATIVE_CLICHES and len(shared) < 2:
        score -= 0.35
    return round(max(0.0, min(1.0, score)), 4)


def select_best_candidate(query: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        text = str(candidate.get("candidate_text", "") or "")
        scored = dict(candidate)
        scored["relevance_score"] = media_relevance_score(query, text)
        ranked.append(scored)
    if not ranked:
        return None
    best = max(ranked, key=lambda item: float(item.get("relevance_score", 0) or 0))
    if float(best.get("relevance_score", 0) or 0) < CONFIG.media_min_relevance_score:
        return None
    return best


def _request(method: str, url: str, **kwargs: Any) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(1, max(1, CONFIG.media_http_max_attempts) + 1):
        try:
            response = requests.request(method, url, timeout=30, **kwargs)
            if response.status_code in RETRYABLE_HTTP_STATUS and attempt < CONFIG.media_http_max_attempts:
                time.sleep(CONFIG.media_http_retry_base_seconds * (2 ** (attempt - 1)))
                continue
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            retryable = status in RETRYABLE_HTTP_STATUS or status is None
            if not retryable or attempt >= CONFIG.media_http_max_attempts:
                raise
            time.sleep(CONFIG.media_http_retry_base_seconds * (2 ** (attempt - 1)))
    assert last_error is not None
    raise last_error


def _download_bytes(url: str) -> bytes:
    return _request("GET", url, headers={"User-Agent": USER_AGENT}).content


def _save_as_jpeg(data: bytes, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGB")
        image = ImageOps.fit(image, (1280, 720), method=Image.Resampling.LANCZOS)
        image.save(destination, "JPEG", quality=88, optimize=True)


def _save_binary(data: bytes, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)


def search_pexels(query: str) -> dict[str, Any] | None:
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        return None
    response = _request(
        "GET",
        "https://api.pexels.com/v1/search",
        params={"query": query, "per_page": 10, "orientation": "landscape"},
        headers={"Authorization": api_key, "User-Agent": USER_AGENT},
    )
    candidates: list[dict[str, Any]] = []
    for photo in response.json().get("photos", []):
        src = photo.get("src", {}) if isinstance(photo, dict) else {}
        download_url = src.get("large2x") or src.get("large")
        if not download_url:
            continue
        alt = _safe_text(photo.get("alt", ""))
        candidates.append({
            "provider": "pexels",
            "download_url": download_url,
            "source_url": photo.get("url", ""),
            "creator": photo.get("photographer", ""),
            "license": "Pexels License",
            "candidate_text": alt,
            "asset_type": "image",
            "mime_type": "image/jpeg",
        })
    return select_best_candidate(query, candidates)


def _best_pexels_video_file(video: dict[str, Any]) -> dict[str, Any] | None:
    files = [
        item for item in (video.get("video_files") or [])
        if isinstance(item, dict)
        and item.get("file_type") == "video/mp4"
        and item.get("link")
        and int(item.get("width", 0) or 0) >= 640
        and int(item.get("height", 0) or 0) >= 360
    ]
    if not files:
        return None

    def rank(item: dict[str, Any]) -> tuple[int, int, int]:
        width = int(item.get("width", 0) or 0)
        height = int(item.get("height", 0) or 0)
        landscape_penalty = 0 if width >= height else 1
        target_penalty = abs(width - 1280) + abs(height - 720)
        oversize_penalty = max(0, width - 1920) + max(0, height - 1080)
        return (landscape_penalty, oversize_penalty, target_penalty)

    return min(files, key=rank)


def search_pexels_video(query: str) -> dict[str, Any] | None:
    """Return a practical landscape Pexels clip for a concrete visual query.

    Pexels Video does not expose reliable descriptive text for semantic rescoring. Therefore the
    manifest records the provider search rank instead of inventing a relevance score from the query
    itself. The calling planner is responsible for issuing concrete, visually meaningful queries.
    """
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        return None
    response = _request(
        "GET",
        "https://api.pexels.com/videos/search",
        params={"query": query, "per_page": 8, "orientation": "landscape", "size": "medium"},
        headers={"Authorization": api_key, "User-Agent": USER_AGENT},
    )
    videos = response.json().get("videos", [])
    ranked: list[tuple[tuple[int, int, int], dict[str, Any]]] = []
    for position, video in enumerate(videos):
        if not isinstance(video, dict):
            continue
        file_info = _best_pexels_video_file(video)
        if not file_info:
            continue
        duration = int(video.get("duration", 0) or 0)
        duration_penalty = 0 if 4 <= duration <= 20 else min(abs(duration - 12), 50)
        resolution_penalty = abs(int(file_info.get("width", 0) or 0) - 1280) + abs(
            int(file_info.get("height", 0) or 0) - 720
        )
        record = {
            "provider": "pexels",
            "download_url": file_info["link"],
            "source_url": video.get("url", ""),
            "creator": (video.get("user") or {}).get("name", ""),
            "license": "Pexels License",
            "candidate_text": "",
            "relevance_score": None,
            "provider_search_rank": position + 1,
            "search_query": query,
            "asset_type": "video",
            "mime_type": "video/mp4",
            "source_duration_seconds": duration,
            "width": file_info.get("width"),
            "height": file_info.get("height"),
        }
        ranked.append(((position, duration_penalty, resolution_penalty), record))
    if not ranked:
        return None
    return min(ranked, key=lambda pair: pair[0])[1]


def search_wikimedia(query: str) -> dict[str, Any] | None:
    response = _request(
        "GET",
        "https://commons.wikimedia.org/w/api.php",
        params={
            "action": "query",
            "generator": "search",
            "gsrsearch": f"{query} filetype:bitmap",
            "gsrnamespace": 6,
            "gsrlimit": 12,
            "prop": "imageinfo",
            "iiprop": "url|mime|extmetadata",
            "iiurlwidth": 1600,
            "format": "json",
            "formatversion": 2,
        },
        headers={"User-Agent": USER_AGENT},
    )
    candidates: list[dict[str, Any]] = []
    for page in response.json().get("query", {}).get("pages", []):
        info_list = page.get("imageinfo") or []
        if not info_list:
            continue
        info = info_list[0]
        if info.get("mime", "") not in {"image/jpeg", "image/png", "image/webp"}:
            continue
        meta = info.get("extmetadata", {})
        license_name = _safe_text(
            meta.get("LicenseShortName", {}).get("value", "")
            or meta.get("UsageTerms", {}).get("value", "")
        )
        license_decision = assess_license("wikimedia_commons", license_name)
        if not license_decision["allowed"]:
            continue
        description = _safe_text(meta.get("ImageDescription", {}).get("value", ""))
        object_name = _safe_text(meta.get("ObjectName", {}).get("value", ""))
        title = _safe_text(page.get("title", ""))
        candidates.append({
            "provider": "wikimedia_commons",
            "download_url": info.get("thumburl") or info.get("url"),
            "source_url": info.get("descriptionurl") or info.get("url", ""),
            "creator": _safe_text(meta.get("Artist", {}).get("value", "")),
            "license": license_name,
            "candidate_text": " ".join(part for part in (title, object_name, description) if part),
            "asset_type": "image",
            "mime_type": info.get("mime", "image/jpeg"),
        })
    return select_best_candidate(query, candidates)


def make_fallback_card(text: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
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


def download_video_shot_asset(
    shot: dict[str, Any], destination: Path, *, logical_file: str | None = None
) -> dict[str, Any] | None:
    query = str(shot.get("visual_query", "") or "").strip()
    if not query:
        return None
    errors: list[str] = []
    try:
        record = search_pexels_video(query)
    except Exception as exc:
        errors.append(f"search_pexels_video: {type(exc).__name__}: {exc}")
        record = None
    if not record:
        return None
    decision = assess_license(str(record.get("provider", "")), str(record.get("license", "")))
    if not decision["allowed"]:
        return None
    try:
        _save_binary(_download_bytes(record["download_url"]), destination)
    except Exception:
        return None
    return {
        "shot_number": shot["shot_number"],
        "visual_query": query,
        "file": logical_file or destination.name,
        "provider": record.get("provider", ""),
        "source_url": record.get("source_url", ""),
        "creator": record.get("creator", ""),
        "license": record.get("license", ""),
        "license_valid": bool(decision["allowed"]),
        "requires_attribution": bool(decision["requires_attribution"]),
        "relevance_score": None,
        "provider_search_rank": record.get("provider_search_rank"),
        "search_query": record.get("search_query", query),
        "candidate_text": "",
        "asset_type": "video",
        "mime_type": "video/mp4",
        "source_duration_seconds": record.get("source_duration_seconds"),
        "errors": errors,
    }


def download_shot_asset(
    shot: dict[str, Any], destination: Path, *, logical_file: str | None = None
) -> dict[str, Any]:
    query = shot["visual_query"]
    errors: list[str] = []
    provider_candidates: list[dict[str, Any]] = []
    for provider in (search_pexels, search_wikimedia):
        try:
            candidate = provider(query)
            if candidate:
                provider_candidates.append(candidate)
        except Exception as exc:
            errors.append(f"{provider.__name__}: {type(exc).__name__}: {exc}")

    record = (
        max(provider_candidates, key=lambda item: float(item.get("relevance_score", 0) or 0))
        if provider_candidates
        else None
    )
    if record:
        decision = assess_license(str(record.get("provider", "")), str(record.get("license", "")))
        if not decision["allowed"]:
            errors.append(f"license: {decision['reason']}")
            record = None
        else:
            try:
                _save_as_jpeg(_download_bytes(record["download_url"]), destination)
            except Exception as exc:
                errors.append(f"download: {type(exc).__name__}: {exc}")
                record = None

    if not record:
        make_fallback_card(shot.get("on_screen_text") or query, destination)
        record = {
            "provider": "generated_fallback",
            "source_url": "",
            "creator": "AI-News-Daily",
            "license": "Generated locally",
            "candidate_text": shot.get("on_screen_text") or query,
            "relevance_score": None,
            "asset_type": "image",
            "mime_type": "image/jpeg",
        }

    decision = assess_license(str(record.get("provider", "")), str(record.get("license", "")))
    return {
        "shot_number": shot["shot_number"],
        "visual_query": query,
        "file": logical_file or destination.name,
        "provider": record.get("provider", ""),
        "source_url": record.get("source_url", ""),
        "creator": record.get("creator", ""),
        "license": record.get("license", ""),
        "license_valid": bool(decision["allowed"]),
        "requires_attribution": bool(decision["requires_attribution"]),
        "relevance_score": record.get("relevance_score"),
        "candidate_text": record.get("candidate_text", ""),
        "asset_type": record.get("asset_type", "image"),
        "mime_type": record.get("mime_type", "image/jpeg"),
        "source_duration_seconds": record.get("source_duration_seconds"),
        "errors": errors,
    }
