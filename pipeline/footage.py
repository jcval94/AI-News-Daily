from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
USER_AGENT = "AI-News-Daily/1.0 (GitHub Actions; footage discovery)"
RETRYABLE_HTTP_STATUS = {408, 409, 429, 500, 502, 503, 504}
STOPWORDS = {
    "a", "al", "and", "artificial", "ai", "de", "del", "el", "en", "for", "ia", "in",
    "inteligencia", "la", "las", "los", "of", "on", "para", "por", "the", "to", "un",
    "una", "y", "with",
}


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char)).lower()


def _tokens(value: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9]+", _fold(value))
        if len(word) >= 3 and word not in STOPWORDS
    }


def _coverage(reference: str, candidate: str) -> float:
    left = _tokens(reference)
    right = _tokens(candidate)
    if not left or not right:
        return 0.0
    shared = left & right
    coverage = len(shared) / len(left)
    jaccard = len(shared) / len(left | right)
    return round((0.8 * coverage) + (0.2 * jaccard), 4)


def _parse_story_date(value: str) -> datetime | None:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _parse_youtube_date(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _date_proximity(story_date: str, published_at: str) -> float:
    story = _parse_story_date(story_date)
    video = _parse_youtube_date(published_at)
    if not story or not video:
        return 0.0
    days = abs((video.date() - story.date()).days)
    if days <= 2:
        return 1.0
    if days <= 7:
        return 0.8
    if days <= 30:
        return 0.45
    if days <= 90:
        return 0.15
    return 0.0


def parse_iso8601_duration(value: str) -> int | None:
    match = re.fullmatch(
        r"P(?:(?P<days>\d+)D)?T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?",
        str(value or ""),
    )
    if not match:
        return None
    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return (((days * 24) + hours) * 60 + minutes) * 60 + seconds


def build_search_queries(story: dict[str, Any], *, limit: int = 2) -> list[str]:
    title = re.sub(r"\s+", " ", str(story.get("title", "") or "")).strip()
    source = re.sub(r"\s+", " ", str(story.get("source", "") or "")).strip()
    summary = re.sub(r"\s+", " ", str(story.get("summary", "") or "")).strip()
    queries: list[str] = []
    if title and source:
        queries.append(f"{title} {source}")
    if title:
        queries.append(title)
    if source and summary:
        summary_words = " ".join(summary.split()[:12])
        queries.append(f"{source} {summary_words}".strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for query in queries:
        normalized = _fold(query)
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(query[:180])
        if len(deduped) >= max(1, limit):
            break
    return deduped


def score_candidate(story: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    title = str(candidate.get("title", "") or "")
    description = str(candidate.get("description", "") or "")
    channel = str(candidate.get("channel_title", "") or "")
    candidate_text = f"{title} {description}".strip()

    title_score = _coverage(str(story.get("title", "") or ""), candidate_text)
    summary_score = _coverage(str(story.get("summary", "") or ""), candidate_text)
    source_score = _coverage(str(story.get("source", "") or ""), channel)
    date_score = _date_proximity(
        str(story.get("date", "") or ""),
        str(candidate.get("published_at", "") or ""),
    )

    relationship_score = round(
        min(1.0, (0.55 * title_score) + (0.18 * summary_score) + (0.17 * source_score) + (0.10 * date_score)),
        4,
    )

    if title_score >= 0.58 and date_score >= 0.45:
        match_type = "DIRECT_EVENT"
    elif source_score >= 0.5 and title_score >= 0.35:
        match_type = "PRIMARY_DEMO"
    elif relationship_score >= 0.28:
        match_type = "CONTEXTUAL_REAL"
    else:
        match_type = "LOW_CONFIDENCE"

    return {
        **candidate,
        "relationship_score": relationship_score,
        "score_components": {
            "title": title_score,
            "summary": summary_score,
            "source_channel": source_score,
            "date_proximity": date_score,
        },
        "footage_type": match_type,
        "source_authority": "PRIMARY_LIKELY" if source_score >= 0.5 else "UNVERIFIED",
        "verification_note": (
            "Classification is metadata-based. Visual/event identity has not been independently verified."
        ),
    }


def rights_record(candidate: dict[str, Any]) -> dict[str, Any]:
    license_name = str(candidate.get("license", "") or "youtube").strip()
    creative_commons = license_name == "creativeCommon"
    return {
        "discoverable": True,
        "embeddable": bool(candidate.get("embeddable", False)),
        "youtube_declared_license": license_name,
        "creative_commons_declared": creative_commons,
        "downloadable_via_youtube_api": False,
        "editable_permission_established": False,
        "publishable_permission_established": False,
        "fair_use_determination": "NOT_ASSESSED",
        "manual_rights_review_required": True,
        "reuse_signal": "CREATIVE_COMMONS_DECLARED" if creative_commons else "STANDARD_YOUTUBE_LICENSE_OR_UNKNOWN",
        "note": (
            "Discovery metadata is not a license opinion. YouTube API footage is never downloaded by this pipeline."
        ),
    }


def _request_json(url: str, *, params: dict[str, Any]) -> dict[str, Any]:
    attempts = max(1, int(os.getenv("YOUTUBE_HTTP_MAX_ATTEMPTS", "3")))
    base_sleep = max(0.0, float(os.getenv("YOUTUBE_HTTP_RETRY_BASE_SECONDS", "1.0")))
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=25)
            if response.status_code in RETRYABLE_HTTP_STATUS and attempt < attempts:
                time.sleep(base_sleep * (2 ** (attempt - 1)))
                continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("YouTube API returned a non-object JSON payload")
            return payload
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            retryable = status in RETRYABLE_HTTP_STATUS or status is None
            if not retryable or attempt >= attempts:
                raise
            time.sleep(base_sleep * (2 ** (attempt - 1)))
    assert last_error is not None
    raise last_error


def search_youtube(query: str, *, api_key: str, max_results: int) -> list[dict[str, Any]]:
    payload = _request_json(
        YOUTUBE_SEARCH_URL,
        params={
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": max(1, min(25, max_results)),
            "order": "relevance",
            "videoEmbeddable": "true",
            "videoSyndicated": "true",
            "safeSearch": "moderate",
            "key": api_key,
        },
    )
    results: list[dict[str, Any]] = []
    for item in payload.get("items", []):
        if not isinstance(item, dict):
            continue
        video_id = str((item.get("id") or {}).get("videoId", "") or "").strip()
        snippet = item.get("snippet") or {}
        if not video_id or not isinstance(snippet, dict):
            continue
        thumbnails = snippet.get("thumbnails") or {}
        thumb = ""
        if isinstance(thumbnails, dict):
            for key in ("high", "medium", "default"):
                value = thumbnails.get(key)
                if isinstance(value, dict) and value.get("url"):
                    thumb = str(value["url"])
                    break
        results.append(
            {
                "video_id": video_id,
                "title": str(snippet.get("title", "") or ""),
                "description": str(snippet.get("description", "") or ""),
                "channel_id": str(snippet.get("channelId", "") or ""),
                "channel_title": str(snippet.get("channelTitle", "") or ""),
                "published_at": str(snippet.get("publishedAt", "") or ""),
                "thumbnail_url": thumb,
                "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
                "embed_url": f"https://www.youtube.com/embed/{video_id}",
            }
        )
    return results


def enrich_videos(candidates: list[dict[str, Any]], *, api_key: str) -> list[dict[str, Any]]:
    ids = list(dict.fromkeys(str(item.get("video_id", "") or "") for item in candidates if item.get("video_id")))
    if not ids:
        return candidates
    details: dict[str, dict[str, Any]] = {}
    for start in range(0, len(ids), 50):
        chunk = ids[start:start + 50]
        payload = _request_json(
            YOUTUBE_VIDEOS_URL,
            params={
                "part": "snippet,contentDetails,status",
                "id": ",".join(chunk),
                "key": api_key,
            },
        )
        for item in payload.get("items", []):
            if not isinstance(item, dict):
                continue
            video_id = str(item.get("id", "") or "")
            status = item.get("status") or {}
            details[video_id] = {
                "duration_seconds": parse_iso8601_duration(str((item.get("contentDetails") or {}).get("duration", "") or "")),
                "embeddable": bool(status.get("embeddable", False)),
                "license": str(status.get("license", "") or "youtube"),
                "privacy_status": str(status.get("privacyStatus", "") or ""),
                "made_for_kids": bool(status.get("madeForKids", False)),
            }
    return [{**candidate, **details.get(str(candidate.get("video_id", "")), {})} for candidate in candidates]


def _evidence_stories(selected: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
    selected_items = selected.get("items", []) if isinstance(selected, dict) else []
    evidence = plan.get("evidence", []) if isinstance(plan, dict) else []
    stories: list[dict[str, Any]] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("selected_news_index", 0) or 0)
        except (TypeError, ValueError):
            continue
        if not (1 <= index <= len(selected_items)):
            continue
        story = selected_items[index - 1]
        if not isinstance(story, dict):
            continue
        stories.append({**story, "evidence_id": str(item.get("evidence_id", "") or "")})
    return stories


def discover_footage(
    *,
    episode_dir: Path,
    output_path: Path,
    api_key: str | None = None,
    max_queries_per_news: int | None = None,
    max_results_per_query: int | None = None,
    max_candidates_per_news: int | None = None,
) -> dict[str, Any]:
    api_key = (api_key or os.getenv("YOUTUBE_API_KEY") or "").strip()
    max_queries = max_queries_per_news or int(os.getenv("YOUTUBE_MAX_QUERIES_PER_NEWS", "2"))
    max_results = max_results_per_query or int(os.getenv("YOUTUBE_MAX_RESULTS_PER_QUERY", "6"))
    max_candidates = max_candidates_per_news or int(os.getenv("YOUTUBE_MAX_CANDIDATES_PER_NEWS", "5"))

    selected = json.loads((episode_dir / "selected_news.json").read_text(encoding="utf-8"))
    plan = json.loads((episode_dir / "episode_plan.json").read_text(encoding="utf-8"))
    stories = _evidence_stories(selected, plan)

    payload: dict[str, Any] = {
        "schema_version": 1,
        "provider": "youtube_data_api_v3",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "policy": {
            "purpose": "Discovery and editorial review only",
            "downloads_youtube_audiovisual_content": False,
            "automatic_fair_use_claims": False,
            "manual_rights_review_required": True,
        },
        "configuration": {
            "max_queries_per_news": max_queries,
            "max_results_per_query": max_results,
            "max_candidates_per_news": max_candidates,
        },
        "items": [],
        "errors": [],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not stories:
        payload["status"] = "no_planned_evidence"
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return payload
    if not api_key:
        payload["status"] = "skipped_missing_api_key"
        payload["errors"].append("YOUTUBE_API_KEY is not configured")
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return payload

    for story in stories:
        queries = build_search_queries(story, limit=max_queries)
        raw_candidates: list[dict[str, Any]] = []
        item_errors: list[str] = []
        seen: set[str] = set()
        for query in queries:
            try:
                found = search_youtube(query, api_key=api_key, max_results=max_results)
            except Exception as exc:
                item_errors.append(f"{type(exc).__name__}: {str(exc)[:300]}")
                continue
            for candidate in found:
                video_id = str(candidate.get("video_id", "") or "")
                if not video_id or video_id in seen:
                    continue
                seen.add(video_id)
                raw_candidates.append({**candidate, "search_query": query})

        if raw_candidates:
            try:
                raw_candidates = enrich_videos(raw_candidates, api_key=api_key)
            except Exception as exc:
                item_errors.append(f"metadata enrichment: {type(exc).__name__}: {str(exc)[:300]}")

        ranked = [score_candidate(story, candidate) for candidate in raw_candidates]
        for candidate in ranked:
            candidate["rights"] = rights_record(candidate)
        ranked.sort(
            key=lambda item: (
                0 if item.get("footage_type") == "DIRECT_EVENT" else
                1 if item.get("footage_type") == "PRIMARY_DEMO" else
                2 if item.get("footage_type") == "CONTEXTUAL_REAL" else 3,
                -float(item.get("relationship_score", 0) or 0),
            )
        )
        ranked = ranked[:max(1, max_candidates)]

        payload["items"].append(
            {
                "news_id": story.get("news_id", ""),
                "evidence_id": story.get("evidence_id", ""),
                "story": {
                    "title": story.get("title", ""),
                    "date": story.get("date", ""),
                    "source": story.get("source", ""),
                    "url": story.get("url", ""),
                },
                "queries": queries,
                "candidate_count": len(ranked),
                "best_candidate": ranked[0] if ranked else None,
                "candidates": ranked,
                "errors": item_errors,
            }
        )
        payload["errors"].extend(
            f"{story.get('news_id', story.get('title', 'story'))}: {error}" for error in item_errors
        )

    if payload["errors"] and payload["items"]:
        payload["status"] = "partial"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover real-footage candidates on YouTube for planned episode evidence")
    parser.add_argument("--episode-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-queries-per-news", type=int, default=None)
    parser.add_argument("--max-results-per-query", type=int, default=None)
    parser.add_argument("--max-candidates-per-news", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = discover_footage(
        episode_dir=Path(args.episode_dir),
        output_path=Path(args.output),
        max_queries_per_news=args.max_queries_per_news,
        max_results_per_query=args.max_results_per_query,
        max_candidates_per_news=args.max_candidates_per_news,
    )
    print(
        f"YouTube footage discovery: status={payload.get('status')} "
        f"stories={len(payload.get('items', []))} errors={len(payload.get('errors', []))}"
    )


if __name__ == "__main__":
    main()
