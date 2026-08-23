from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pipeline.run as base
from pipeline.evidence_reconciliation import reconcile_evidence_indices

# This module is intentionally experimental. Production still executes pipeline.run.
# The default experiment keeps every selected story's exact factual source while removing
# raw source material that the Selector already rejected from downstream repeated prompts.
_ALLOWED_MODES = {"off", "conservative", "strict"}
_FACTUAL_AGENT_NAMES = {
    "essay_script_writer",
    "script_critic",
    "script_refiner",
}
_COMPACT_AGENT_NAMES = _FACTUAL_AGENT_NAMES | {"seo_master"}

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


def _configured_mode() -> str:
    mode = os.getenv("COST_CONTEXT_MODE", "conservative").strip().lower()
    return mode if mode in _ALLOWED_MODES else "conservative"


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


def _validated_reconciled_plan(
    plan: dict[str, Any], selection: dict[str, Any]
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    items = selection.get("items", []) if isinstance(selection, dict) else []
    if not isinstance(items, list) or not items:
        return None, []
    reconciled, changes = reconcile_evidence_indices(plan, selection)
    # Keep runtime agent context schema-clean. Reconciliation telemetry is carried separately.
    reconciled = dict(reconciled)
    reconciled.pop("evidence_reconciliation", None)
    try:
        base.validate_episode_plan(reconciled, len(items))
    except (TypeError, ValueError):
        return None, changes
    return reconciled, changes


def _evidence_index_map(
    plan: dict[str, Any], item_count: int
) -> tuple[set[int], dict[int, list[dict[str, Any]]]] | None:
    evidence = plan.get("evidence", []) if isinstance(plan, dict) else []
    if not isinstance(evidence, list) or not evidence:
        return None
    used_indices: set[int] = set()
    evidence_by_index: dict[int, list[dict[str, Any]]] = {}
    try:
        for entry in evidence:
            if not isinstance(entry, dict):
                return None
            index = int(entry.get("selected_news_index", 0) or 0)
            if index < 1 or index > item_count:
                return None
            used_indices.add(index)
            evidence_by_index.setdefault(index, []).append(entry)
    except (TypeError, ValueError):
        return None
    return used_indices, evidence_by_index


def _selection_item(
    raw_item: dict[str, Any],
    *,
    position: int,
    planned: bool,
    mode: str,
    evidence_roles: list[dict[str, Any]],
) -> dict[str, Any]:
    if mode == "strict" and not planned:
        # Aggressive comparison arm only: preserve positional/provenance semantics but
        # expose no unused headline that could tempt a downstream model to reuse it.
        return {
            "news_id": raw_item.get("news_id", ""),
            "source_locator": raw_item.get("source_locator", ""),
            "selected_news_index": position,
            "omitted_unused_evidence": True,
        }

    # Conservative arm: retain metadata, summary and why_it_matters for every selected
    # story. Exact raw factual text lives in news_text to avoid duplicating it twice.
    compact_item = {
        key: raw_item.get(key)
        for key in _SELECTION_FIELDS
        if raw_item.get(key) not in (None, "")
    }
    compact_item["selected_news_index"] = position
    compact_item["planned_evidence"] = planned
    if planned:
        compact_item["evidence_roles"] = evidence_roles
    return compact_item


def compact_agent_state(
    agent: Any,
    state: dict[str, Any],
    *,
    mode: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Reduce repeated model context without removing selected factual evidence.

    Safety rules:
    - selector/director/attention/voice keep their existing state;
    - evidence indices are high-confidence reconciled and revalidated before scoping;
    - conservative mode keeps title/source/URL/summary/why_it_matters for ALL selected news;
    - conservative factual agents keep exact raw_content for ALL selected news in news_text;
    - strict mode keeps exact raw factual text only for planned evidence and is comparison-only;
    - malformed or ambiguous state fails open to the original full context.
    """

    agent_name = str(getattr(agent, "name", "") or "")
    selected_mode = (mode or _configured_mode()).strip().lower()
    if selected_mode not in _ALLOWED_MODES:
        selected_mode = "conservative"
    if selected_mode == "off" or agent_name not in _COMPACT_AGENT_NAMES:
        return state, None

    selection = _json_dict(state.get("selected_news"))
    plan = _json_dict(state.get("episode_plan"))
    if not selection or not plan:
        return state, None

    items = selection.get("items", [])
    if not isinstance(items, list) or not items or not all(isinstance(item, dict) for item in items):
        return state, None

    reconciled_plan, reconciliation_changes = _validated_reconciled_plan(plan, selection)
    if reconciled_plan is None:
        return state, None
    mapped = _evidence_index_map(reconciled_plan, len(items))
    if mapped is None:
        return state, None
    used_indices, evidence_by_index = mapped

    compact_items: list[dict[str, Any]] = []
    raw_sources: list[dict[str, Any]] = []
    evidence_hashes: dict[str, str] = {}

    for position, raw_item in enumerate(items, start=1):
        planned = position in used_indices
        evidence_roles = [
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
        compact_items.append(
            _selection_item(
                raw_item,
                position=position,
                planned=planned,
                mode=selected_mode,
                evidence_roles=evidence_roles,
            )
        )

        # Conservative factual agents retain exact raw facts for every selected story.
        # Strict mode is the evidence-only comparison arm.
        retain_raw = selected_mode == "conservative" or planned
        if not retain_raw:
            continue
        raw_content = str(raw_item.get("raw_content", "") or _fallback_raw(raw_item))
        if not raw_content.strip():
            # If the raw source cannot be preserved as promised, fail open rather than
            # silently weakening factual review.
            if agent_name in _FACTUAL_AGENT_NAMES:
                return state, None
            continue
        raw_sources.append(
            {
                "selected_news_index": position,
                "news_id": raw_item.get("news_id", ""),
                "source_locator": raw_item.get("source_locator", ""),
                "url_quality": raw_item.get("url_quality", ""),
                "raw_content": raw_content,
                "planned_evidence": planned,
            }
        )
        if planned:
            for role in evidence_roles:
                evidence_id = str(role.get("evidence_id", "") or "")
                if evidence_id:
                    evidence_hashes[evidence_id] = hashlib.sha256(
                        raw_content.encode("utf-8")
                    ).hexdigest()

    compact_selection = {
        "schema_version": 1,
        "items": compact_items,
        "context_scope": f"selected_news_metadata_{selected_mode}",
    }
    compact_news = {
        "schema_version": 1,
        "items": raw_sources,
        "context_scope": (
            "all_selected_news_raw" if selected_mode == "conservative"
            else "episode_plan_evidence_raw_only"
        ),
    }

    before_selected = str(state.get("selected_news", "") or "")
    before_news = str(state.get("news_text", "") or "")
    selected_json = json.dumps(compact_selection, ensure_ascii=False, separators=(",", ":"))
    news_json = json.dumps(compact_news, ensure_ascii=False, separators=(",", ":"))
    plan_json = json.dumps(reconciled_plan, ensure_ascii=False, separators=(",", ":"))

    compacted = dict(state)
    compacted["selected_news"] = selected_json
    compacted["episode_plan"] = plan_json
    if agent_name in _FACTUAL_AGENT_NAMES and "news_text" in compacted:
        compacted["news_text"] = news_json

    before_chars = len(before_selected)
    after_chars = len(selected_json)
    if agent_name in _FACTUAL_AGENT_NAMES and "news_text" in state:
        before_chars += len(before_news)
        after_chars += len(news_json)

    stats = {
        "mode": selected_mode,
        "selected_item_count": len(items),
        "raw_source_item_count": len(raw_sources),
        "used_evidence_item_count": len(used_indices),
        "used_evidence_indices": sorted(used_indices),
        "evidence_reconciliation_count": len(reconciliation_changes),
        "evidence_reconciliation": reconciliation_changes,
        "retained_evidence_sha256": evidence_hashes,
        "context_chars_before": before_chars,
        "context_chars_after": after_chars,
        "context_char_reduction_pct": round(
            (1.0 - (after_chars / before_chars)) * 100.0, 1
        )
        if before_chars > 0
        else 0.0,
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
    agent_name = str(getattr(agent, "name", "") or "")

    # Director must see the complete catalog. Once it has chosen evidence, repair only
    # deterministic/high-confidence evidence-id/index mismatches BEFORE the plan is persisted,
    # written, judged or used for any cost scoping.
    if agent_name == "editorial_director":
        result = await _ORIGINAL_RUN_AGENT(
            agent,
            initial_state,
            prompt,
            step=step,
            trace=trace,
            iteration=iteration,
        )
        selection = _json_dict(initial_state.get("selected_news"))
        plan = _json_dict(result.get("episode_plan"))
        if selection and plan:
            reconciled, changes = _validated_reconciled_plan(plan, selection)
            if reconciled is not None:
                result = dict(result)
                result["episode_plan"] = reconciled
                if changes and trace:
                    trace[-1]["evidence_reconciliation"] = {
                        "changed_count": len(changes),
                        "changes": changes,
                    }
        return result

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
    """Run the production pipeline with experimental evidence-safe context scoping."""
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
