from __future__ import annotations

import hashlib
import json
from typing import Any

_INDEX_FIELDS = (
    "news_id",
    "source_file",
    "source_locator",
    "item_index",
    "title",
    "date",
    "date_origin",
    "source",
    "url",
    "url_quality",
    "category",
)


def _as_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def build_source_harness(
    selection: dict[str, Any],
    *,
    discovery_item_count: int | None = None,
    discovery_context_chars: int | None = None,
) -> dict[str, Any]:
    """Build a progressive-disclosure view over the Selector shortlist.

    The persisted ``selected_news.json`` remains the canonical full selection artifact.
    This harness is only the runtime view given to downstream agents:

    1. ``selected_news`` becomes a lightweight index of the selected stories.
    2. ``news_text`` contains the exact raw source block for those same selected stories.
    3. Stories rejected by the Selector are no longer repeated downstream.

    Nothing is summarized by another model, embedded, or rewritten. If the exact raw
    source block is unavailable the function fails instead of silently weakening evidence.
    """

    items = selection.get("items", []) if isinstance(selection, dict) else []
    if not isinstance(items, list) or not items:
        raise ValueError("Cannot build source harness without selected news")
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("selected_news.items must contain only objects")

    index_items: list[dict[str, Any]] = []
    source_items: list[dict[str, Any]] = []
    manifest_items: list[dict[str, Any]] = []

    for position, item in enumerate(items, start=1):
        news_id = str(item.get("news_id", "") or "").strip()
        source_locator = str(item.get("source_locator", "") or "").strip()
        raw_content = str(item.get("raw_content", "") or "").strip()
        if not news_id:
            raise ValueError(f"Selected source {position} has no news_id")
        if not source_locator:
            raise ValueError(f"Selected source {news_id!r} has no source_locator")
        if not raw_content:
            raise ValueError(f"Selected source {news_id!r} has no raw_content")

        index_item = {
            key: item.get(key)
            for key in _INDEX_FIELDS
            if item.get(key) not in (None, "")
        }
        index_item["selected_news_index"] = position
        selection_reason = str(item.get("selection_reason", "") or "").strip()
        if selection_reason:
            index_item["selection_reason"] = selection_reason
        index_items.append(index_item)

        source_items.append(
            {
                "selected_news_index": position,
                "news_id": news_id,
                "source_locator": source_locator,
                "url": str(item.get("url", "") or ""),
                "url_quality": str(item.get("url_quality", "") or ""),
                "raw_content": raw_content,
            }
        )
        manifest_items.append(
            {
                "selected_news_index": position,
                "news_id": news_id,
                "source_locator": source_locator,
                "raw_content_sha256": hashlib.sha256(
                    raw_content.encode("utf-8")
                ).hexdigest(),
            }
        )

    selected_news_view = {
        "schema_version": 1,
        "context_scope": "selected_story_index",
        "items": index_items,
        "discarded_duplicates": selection.get("discarded_duplicates", []),
        "selection_notes": selection.get("selection_notes", []),
    }
    news_text_view = {
        "schema_version": 1,
        "context_scope": "selected_exact_sources",
        "items": source_items,
    }

    selected_news_json = json.dumps(
        selected_news_view, ensure_ascii=False, separators=(",", ":")
    )
    news_text_json = json.dumps(
        news_text_view, ensure_ascii=False, separators=(",", ":")
    )
    harness_chars = len(selected_news_json) + len(news_text_json)

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "strategy": "progressive_disclosure_after_selector",
        "selected_item_count": len(items),
        "selected_sources": manifest_items,
        "runtime_context_chars": harness_chars,
        "guarantees": {
            "exact_raw_content_for_every_selected_story": True,
            "model_generated_summaries": False,
            "embeddings_or_vector_database": False,
            "rejected_discovery_items_forwarded_downstream": False,
        },
    }
    if discovery_item_count is not None:
        manifest["discovery_item_count"] = max(0, int(discovery_item_count))
        manifest["omitted_after_selection_count"] = max(
            0, int(discovery_item_count) - len(items)
        )
    if discovery_context_chars is not None:
        before = max(0, int(discovery_context_chars)) + len(
            json.dumps(selection, ensure_ascii=False)
        )
        manifest["legacy_downstream_context_chars"] = before
        manifest["runtime_context_char_reduction_pct"] = (
            round((1.0 - harness_chars / before) * 100.0, 1) if before else 0.0
        )

    return {
        "selected_news": selected_news_view,
        "news_text": news_text_view,
        "selected_news_json": selected_news_json,
        "news_text_json": news_text_json,
        "manifest": manifest,
    }


def build_source_harness_from_state(
    state: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Replace only downstream source payloads in an ADK state dictionary.

    Fail-open behavior is intentional for the experimental runner: if the state is not
    yet past selection, return it unchanged rather than guessing at missing evidence.
    """

    selection = _as_dict(state.get("selected_news"))
    if not selection or not selection.get("items"):
        return state, None
    try:
        harness = build_source_harness(selection)
    except ValueError:
        return state, None

    result = dict(state)
    result["selected_news"] = harness["selected_news_json"]
    if "news_text" in result:
        result["news_text"] = harness["news_text_json"]
    return result, harness["manifest"]
