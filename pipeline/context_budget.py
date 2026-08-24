from __future__ import annotations

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

_SELECTED_INDEX_AGENTS = {
    "editorial_director",
    "essay_script_writer",
    "script_critic",
    "script_refiner",  # legacy compatibility
    "factual_script_refiner",
    "seo_master",
}

_REFINER_AGENTS = {
    "script_refiner",  # legacy compatibility
    "factual_script_refiner",
    "voice_script_refiner",
    "secondary_script_refiner",
}

_COMPACT_JSON_KEYS = {
    "news_text",
    "previous_selected_news",
    "previous_essays",
    "novelty_feedback",
    "selected_news",
    "episode_plan",
    "review",
    "seo_review",
    "attention_review",
    "voice_review",
    "timeline_slots",
}


def _json_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def compact_json(value: Any) -> str:
    """Serialize model-only JSON without changing its data."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def build_selected_news_index(selection: dict[str, Any]) -> dict[str, Any]:
    """Replace duplicated selected-story bodies with pointers into full news_text.

    The full persisted selected_news.json remains unchanged. This runtime index only
    removes fields already present verbatim in news_text; no discovery source is
    removed or summarized.
    """
    items = selection.get("items", []) if isinstance(selection, dict) else []
    if not isinstance(items, list) or not items:
        raise ValueError("Cannot index an empty selected_news payload")
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("selected_news.items must contain only objects")

    indexed: list[dict[str, Any]] = []
    for position, item in enumerate(items, start=1):
        news_id = str(item.get("news_id", "") or "").strip()
        source_locator = str(item.get("source_locator", "") or "").strip()
        if not news_id or not source_locator:
            raise ValueError("Every selected item needs news_id and source_locator")
        row = {
            key: item.get(key)
            for key in _INDEX_FIELDS
            if item.get(key) not in (None, "")
        }
        row["selected_news_index"] = position
        selection_reason = str(item.get("selection_reason", "") or "").strip()
        if selection_reason:
            row["selection_reason"] = selection_reason
        indexed.append(row)

    return {
        "schema_version": 1,
        "context_scope": "selected_story_index_full_discovery_retained",
        "items": indexed,
        "discarded_duplicates": selection.get("discarded_duplicates", []),
        "selection_notes": selection.get("selection_notes", []),
    }


def _validate_full_discovery_retention(
    selection: dict[str, Any], discovery: dict[str, Any]
) -> dict[str, Any]:
    selected_items = selection.get("items", []) if isinstance(selection, dict) else []
    discovery_items = discovery.get("items", []) if isinstance(discovery, dict) else []
    if not isinstance(selected_items, list) or not isinstance(discovery_items, list):
        raise ValueError("Source context must expose list-valued items")

    discovery_by_id = {
        str(item.get("news_id", "") or ""): item
        for item in discovery_items
        if isinstance(item, dict) and item.get("news_id")
    }
    exact_selected = 0
    for item in selected_items:
        if not isinstance(item, dict):
            raise ValueError("selected_news contains a non-object item")
        news_id = str(item.get("news_id", "") or "")
        source = discovery_by_id.get(news_id)
        if source is None:
            raise ValueError(f"Selected source {news_id!r} is absent from news_text")
        if item.get("raw_content") != source.get("raw_content"):
            raise ValueError(f"Selected source {news_id!r} raw_content differs from news_text")
        if item.get("source_locator") != source.get("source_locator"):
            raise ValueError(f"Selected source {news_id!r} source_locator differs from news_text")
        exact_selected += 1

    return {
        "discovery_item_count": len(discovery_items),
        "selected_item_count": len(selected_items),
        "selected_exact_source_matches": exact_selected,
    }


def build_context_budget(
    selection: dict[str, Any], discovery_json: str
) -> dict[str, Any]:
    """Build a no-source-loss runtime view and an auditable manifest."""
    discovery = _json_object(discovery_json)
    if discovery is None:
        raise ValueError("news_text is not valid JSON")
    integrity = _validate_full_discovery_retention(selection, discovery)
    selected_index = build_selected_news_index(selection)
    optimized_news_text = compact_json(discovery)
    optimized_selected_news = compact_json(selected_index)

    if json.loads(optimized_news_text) != discovery:
        raise ValueError("Optimized news_text changed source data")

    legacy_selected = json.dumps(selection, ensure_ascii=False)
    manifest = {
        "schema_version": 1,
        "strategy": "no_source_loss_context_deduplication",
        **integrity,
        "discovery_item_count_after": integrity["discovery_item_count"],
        "removed_source_items": 0,
        "all_discovery_sources_preserved": True,
        "model_generated_source_summaries": False,
        "selected_source_bodies_deduplicated": True,
        "legacy_selected_news_chars": len(legacy_selected),
        "runtime_selected_index_chars": len(optimized_selected_news),
        "legacy_news_text_chars": len(discovery_json),
        "runtime_news_text_chars": len(optimized_news_text),
    }
    return {
        "selected_news": selected_index,
        "selected_news_json": optimized_selected_news,
        "news_text_json": optimized_news_text,
        "manifest": manifest,
    }


def optimize_agent_state(
    agent_name: str, state: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compact repeated model context while preserving the complete discovery corpus.

    If source-integrity validation cannot be proven, fail open and return the original
    state. Cost optimization must never weaken a valid production run.

    Only the factual refiner is source-aware. Voice and secondary refiners deliberately
    receive no discovery corpus, preserving the refinement-isolation contract.
    """
    result = dict(state)
    before_chars = sum(len(str(value or "")) for value in state.values())
    applied_selected_index = False
    source_integrity_verified = False
    fail_open_reason = ""

    if agent_name in _SELECTED_INDEX_AGENTS:
        selection = _json_object(state.get("selected_news"))
        discovery = _json_object(state.get("news_text"))
        if selection and discovery:
            try:
                _validate_full_discovery_retention(selection, discovery)
                result["selected_news"] = compact_json(build_selected_news_index(selection))
                source_integrity_verified = True
                applied_selected_index = True
            except ValueError as exc:
                fail_open_reason = str(exc)

    if not fail_open_reason:
        for key in _COMPACT_JSON_KEYS:
            if key not in result or not isinstance(result[key], str):
                continue
            try:
                parsed = json.loads(result[key])
            except json.JSONDecodeError:
                continue
            result[key] = compact_json(parsed)

        if agent_name in _REFINER_AGENTS and result.get("sectioned_draft_script"):
            result.pop("draft_script", None)

    after_chars = sum(len(str(value or "")) for value in result.values())
    summary = {
        "strategy": "no_source_loss_context_deduplication",
        "applied": not bool(fail_open_reason),
        "selected_index_applied": applied_selected_index,
        "source_integrity_verified": source_integrity_verified,
        "removed_source_items": 0,
        "state_chars_before": before_chars,
        "state_chars_after": after_chars,
        "state_chars_saved": max(0, before_chars - after_chars),
    }
    if fail_open_reason:
        summary["fail_open_reason"] = fail_open_reason
    return (state if fail_open_reason else result), summary
