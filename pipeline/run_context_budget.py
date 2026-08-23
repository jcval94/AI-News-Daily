from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pipeline.run as base
from pipeline.context_budget import build_context_budget, optimize_agent_state

_ORIGINAL_RUN_AGENT = base.run_agent


def _enabled() -> bool:
    return os.getenv("CONTEXT_BUDGET_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _annotate_latest_trace(
    trace: list[dict[str, Any]], value: dict[str, Any]
) -> None:
    if trace and isinstance(trace[-1], dict):
        trace[-1]["context_budget"] = value


async def _run_agent_with_context_budget(
    agent: Any,
    initial_state: dict[str, Any],
    prompt: str,
    *,
    step: str,
    trace: list[dict[str, Any]],
    iteration: int | None = None,
) -> dict[str, Any]:
    runtime_state = initial_state
    summary: dict[str, Any] | None = None
    if _enabled():
        agent_name = str(getattr(agent, "name", "") or "")
        runtime_state, summary = optimize_agent_state(agent_name, initial_state)

    result = await _ORIGINAL_RUN_AGENT(
        agent,
        runtime_state,
        prompt,
        step=step,
        trace=trace,
        iteration=iteration,
    )
    if summary:
        _annotate_latest_trace(trace, summary)
    return result


async def build(**kwargs: Any) -> Path | None:
    """Run the normal pipeline with no-source-loss context deduplication."""
    previous = base.run_agent
    base.run_agent = _run_agent_with_context_budget
    try:
        result = await base.build(**kwargs)
    finally:
        base.run_agent = previous

    if result is not None and _enabled():
        selected_path = result / "selected_news.json"
        if selected_path.exists():
            try:
                selection = json.loads(selected_path.read_text(encoding="utf-8"))
                if selection.get("items"):
                    news_text, _, _, _ = base.collect_available_news(
                        kwargs["news_dir"], kwargs["target_date"]
                    )
                    budget = build_context_budget(selection, news_text)
                    base.write_json(result / "context_budget.json", budget["manifest"])
            except (OSError, ValueError, json.JSONDecodeError):
                # Observability must never turn an otherwise valid run into a failure.
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
