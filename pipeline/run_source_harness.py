from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pipeline.run as base
from pipeline.evidence_reconciliation import reconcile_evidence_indices
from pipeline.source_harness import build_source_harness, build_source_harness_from_state

_ORIGINAL_RUN_AGENT = base.run_agent
_HARNESS_AGENT_NAMES = {
    "editorial_director",
    "essay_script_writer",
    "script_critic",
    "script_refiner",
    "seo_master",
}


def _enabled() -> bool:
    return os.getenv("SOURCE_HARNESS_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


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


def _annotate_latest_trace(
    trace: list[dict[str, Any]], key: str, value: dict[str, Any]
) -> None:
    if trace and isinstance(trace[-1], dict):
        trace[-1][key] = value


async def _run_agent_with_source_harness(
    agent: Any,
    initial_state: dict[str, Any],
    prompt: str,
    *,
    step: str,
    trace: list[dict[str, Any]],
    iteration: int | None = None,
) -> dict[str, Any]:
    agent_name = str(getattr(agent, "name", "") or "")
    runtime_state = initial_state
    harness_manifest: dict[str, Any] | None = None

    if _enabled() and agent_name in _HARNESS_AGENT_NAMES:
        runtime_state, harness_manifest = build_source_harness_from_state(initial_state)

    result = await _ORIGINAL_RUN_AGENT(
        agent,
        runtime_state,
        prompt,
        step=step,
        trace=trace,
        iteration=iteration,
    )

    if harness_manifest:
        _annotate_latest_trace(
            trace,
            "source_harness",
            {
                "strategy": harness_manifest["strategy"],
                "selected_item_count": harness_manifest["selected_item_count"],
                "runtime_context_chars": harness_manifest["runtime_context_chars"],
            },
        )

    # A source harness is only safe if the plan points at the intended selected sources.
    # Reconcile only the repository's existing high-confidence semantic mismatches, then
    # re-run the deterministic structural validator before any writer/judge sees the plan.
    if agent_name == "editorial_director":
        selection = _json_dict(initial_state.get("selected_news"))
        episode_plan = _json_dict(result.get("episode_plan"))
        if selection and episode_plan:
            reconciled, changes = reconcile_evidence_indices(episode_plan, selection)
            reconciled = dict(reconciled)
            reconciled.pop("evidence_reconciliation", None)
            base.validate_episode_plan(reconciled, len(selection.get("items", [])))
            result = dict(result)
            result["episode_plan"] = reconciled
            if changes:
                _annotate_latest_trace(
                    trace,
                    "evidence_reconciliation",
                    {"changed_count": len(changes), "changes": changes},
                )

    return result


async def build(**kwargs: Any) -> Path | None:
    """Run the normal production pipeline with progressive source disclosure enabled."""

    previous = base.run_agent
    base.run_agent = _run_agent_with_source_harness
    try:
        result = await base.build(**kwargs)
    finally:
        base.run_agent = previous

    # Persist an audit-only manifest. Canonical source data remains selected_news.json;
    # this file records what the runtime harness exposed, never a second source of truth.
    if result is not None and _enabled():
        selected_path = result / "selected_news.json"
        if selected_path.exists():
            try:
                selection = json.loads(selected_path.read_text(encoding="utf-8"))
                if selection.get("items"):
                    news_text, _, _, source_items = base.collect_available_news(
                        kwargs["news_dir"], kwargs["target_date"]
                    )
                    harness = build_source_harness(
                        selection,
                        discovery_item_count=len(source_items),
                        discovery_context_chars=len(news_text),
                    )
                    base.write_json(result / "source_harness.json", harness["manifest"])
            except (OSError, ValueError, json.JSONDecodeError):
                # The pipeline result remains authoritative; audit telemetry must never
                # turn an otherwise valid episode into a failure.
                pass

    return result


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
