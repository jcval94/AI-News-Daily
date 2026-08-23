from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pipeline.run as base

# Only stages after the Editorial Director has fixed the evidence set are eligible.
# Selection and episode planning must continue seeing the complete news window.
_COMPACT_AGENT_NAMES = {
    "essay_script_writer",
    "script_critic",
    "seo_master",
    "script_refiner",
}

_SELECTION_FIELDS = (
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
    "summary",
    "why_it_matters",
)


def _json_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _fallback_raw(item: dict[str, Any]) -> str:
    parts = [
        str(item.get("title", "") or ""),
        f"Fecha: {item.get('date', '')}" if item.get("date") else "",
        f"Fuente: {item.get('source', '')}" if item.get("source") else "",
        f"Enlace: {item.get('url', '')}" if item.get("url") else "",
        f"Resumen: {item.get('summary', '')}" if item.get("summary") else "",
        f"Por qué importa: {item.get('why_it_matters', '')}" if item.get("why_it_matters") else "",
    ]
    return "\n".join(part for part in parts if part)


def compact_agent_state(agent: Any, state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Scope repeated model context to evidence already chosen by the Editorial Director.

    The compact representation preserves the original selected-news list length so the
    1-based selected_news_index values in episode_plan keep their exact meaning. Unused
    stories become provenance-only stubs; factual raw text is retained only for evidence
    the plan actually references. If anything is malformed, fail open and return the
    original state rather than risking loss of evidence.
    """

    agent_name = str(getattr(agent, "name", "") or "")
    if agent_name not in _COMPACT_AGENT_NAMES:
        return state, None

    selection = _json_dict(state.get("selected_news"))
    plan = _json_dict(state.get("episode_plan"))
    if not selection or not plan:
        return state, None

    items = selection.get("items", [])
    evidence = plan.get("evidence", [])
    if not isinstance(items, list) or not isinstance(evidence, list) or not items or not evidence:
        return state, None

    used_indices: set[int] = set()
    evidence_by_index: dict[int, list[dict[str, Any]]] = {}
    try:
        for entry in evidence:
            if not isinstance(entry, dict):
                return state, None
            index = int(entry.get("selected_news_index", 0) or 0)
            if index < 1 or index > len(items):
                return state, None
            used_indices.add(index)
            evidence_by_index.setdefault(index, []).append(entry)
    except (TypeError, ValueError):
        return state, None

    compact_items: list[dict[str, Any]] = []
    raw_evidence: list[dict[str, Any]] = []
    for position, raw_item in enumerate(items, start=1):
        if not isinstance(raw_item, dict):
            return state, None

        if position not in used_indices:
            # Keep positional semantics without paying to resend unused summaries/raw text.
            compact_items.append(
                {
                    "news_id": raw_item.get("news_id", ""),
                    "source_locator": raw_item.get("source_locator", ""),
                    "title": raw_item.get("title", ""),
                    "omitted_unused_evidence": True,
                }
            )
            continue

        compact_item = {
            key: raw_item.get(key)
            for key in _SELECTION_FIELDS
            if raw_item.get(key) not in (None, "")
        }
        compact_item["selected_news_index"] = position
        compact_item["evidence_roles"] = [
            {
                key: entry.get(key)
                for key in (
                    "evidence_id",
                    "role",
                    "argument_role",
                    "narrative_function",
                    "skepticism_angle",
                    "human_stakes",
                )
                if entry.get(key) not in (None, "")
            }
            for entry in evidence_by_index.get(position, [])
        ]
        compact_items.append(compact_item)

        raw_evidence.append(
            {
                "selected_news_index": position,
                "news_id": raw_item.get("news_id", ""),
                "source_locator": raw_item.get("source_locator", ""),
                "url_quality": raw_item.get("url_quality", ""),
                "raw_content": str(raw_item.get("raw_content", "") or _fallback_raw(raw_item)),
            }
        )

    compact_selection = {
        "schema_version": 1,
        "items": compact_items,
        "context_scope": "episode_plan_evidence_only",
    }
    compact_news = {
        "schema_version": 1,
        "items": raw_evidence,
        "context_scope": "episode_plan_evidence_only",
    }

    before_selected = str(state.get("selected_news", "") or "")
    before_news = str(state.get("news_text", "") or "")
    selected_json = json.dumps(compact_selection, ensure_ascii=False, separators=(",", ":"))
    news_json = json.dumps(compact_news, ensure_ascii=False, separators=(",", ":"))

    compacted = dict(state)
    compacted["selected_news"] = selected_json
    if "news_text" in compacted:
        compacted["news_text"] = news_json

    before_chars = len(before_selected) + len(before_news)
    after_chars = len(selected_json) + (len(news_json) if "news_text" in compacted else 0)
    stats = {
        "mode": "episode_plan_evidence_only",
        "selected_item_count": len(items),
        "used_evidence_item_count": len(used_indices),
        "context_chars_before": before_chars,
        "context_chars_after": after_chars,
        "context_char_reduction_pct": round(
            (1.0 - (after_chars / before_chars)) * 100.0, 1
        ) if before_chars > 0 else 0.0,
    }
    return compacted, stats


_ORIGINAL_RUN_AGENT = base.run_agent


async def _cost_aware_run_agent(
    agent: Any,
    initial_state: dict[str, Any],
    prompt: str,
    *,
    step: str,
    trace: list[dict[str, Any]],
    iteration: int | None = None,
) -> dict[str, Any]:
    compacted_state, stats = compact_agent_state(agent, initial_state)
    result = await _ORIGINAL_RUN_AGENT(
        agent,
        compacted_state,
        prompt,
        step=step,
        trace=trace,
        iteration=iteration,
    )
    if stats and trace:
        trace[-1]["context_compaction"] = stats
    return result


async def build(**kwargs: Any) -> Path | None:
    """Run the production pipeline with evidence-scoped repeated contexts."""
    previous = base.run_agent
    base.run_agent = _cost_aware_run_agent
    try:
        return await base.build(**kwargs)
    finally:
        base.run_agent = previous


def main() -> None:
    args = base.parse_args()
    asyncio.run(
        build(
            target_date=base.parse_target_date(args.target_date),
            news_dir=Path(args.news_dir),
            scripts_root=Path(args.scripts_dir),
            multimedia_root=Path(args.multimedia_dir),
            history_scripts_root=Path(args.history_scripts_dir),
            max_media_downloads=args.max_media_downloads,
            download_multimedia=base.DOWNLOAD_MULTIMEDIA and not args.no_download_multimedia,
            editorial_dir=Path(args.editorial_dir),
        )
    )


if __name__ == "__main__":
    main()
