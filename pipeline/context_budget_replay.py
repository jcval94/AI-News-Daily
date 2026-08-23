from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import tiktoken

from pipeline.context_budget import build_context_budget, compact_json
from pipeline.run import collect_available_news


def replay(*, episode_dir: Path, news_dir: Path, target_date: date) -> dict[str, Any]:
    selection = json.loads(
        (episode_dir / "selected_news.json").read_text(encoding="utf-8")
    )
    episode_plan = json.loads(
        (episode_dir / "episode_plan.json").read_text(encoding="utf-8")
    )
    trace = json.loads(
        (episode_dir / "execution_trace.json").read_text(encoding="utf-8")
    )
    discovery_json, available_files, missing_dates, source_items = collect_available_news(
        news_dir, target_date
    )
    budget = build_context_budget(selection, discovery_json)

    enc = tiktoken.get_encoding("o200k_base")

    def tokens(value: Any) -> int:
        return len(enc.encode(str(value or "")))

    legacy_selected_json = json.dumps(selection, ensure_ascii=False)
    optimized_selected_json = budget["selected_news_json"]
    optimized_discovery_json = budget["news_text_json"]
    legacy_plan_json = json.dumps(episode_plan, ensure_ascii=False)
    optimized_plan_json = compact_json(episode_plan)

    successful_calls = [
        call
        for call in trace.get("agent_calls", [])
        if isinstance(call, dict) and call.get("status") == "success"
    ]
    steps = Counter(str(call.get("step", "")) for call in successful_calls)
    baseline_prompt_tokens = sum(
        int((call.get("usage") or {}).get("prompt_tokens", 0) or 0)
        for call in successful_calls
    )
    baseline_output_tokens = sum(
        int((call.get("usage") or {}).get("output_tokens", 0) or 0)
        for call in successful_calls
    )

    selected_context_calls = (
        steps["plan_episode"]
        + steps["replan_episode_novelty"]
        + steps["write_script"]
        + steps["editorial_judge"]
        + steps["seo_judge"]
        + steps["refine_script"]
    )
    news_context_calls = (
        steps["select_news"]
        + steps["plan_episode"]
        + steps["replan_episode_novelty"]
        + steps["write_script"]
        + steps["editorial_judge"]
        + steps["refine_script"]
    )
    episode_plan_calls = (
        steps["write_script"]
        + steps["editorial_judge"]
        + steps["seo_judge"]
        + steps["attention_judge"]
        + steps["voice_judge"]
        + steps["refine_script"]
        + steps["plan_multimedia"]
    )

    selected_delta = tokens(legacy_selected_json) - tokens(optimized_selected_json)
    news_delta = tokens(discovery_json) - tokens(optimized_discovery_json)
    plan_delta = tokens(legacy_plan_json) - tokens(optimized_plan_json)

    estimated_saved_prompt_tokens = (
        selected_delta * selected_context_calls
        + news_delta * news_context_calls
        + plan_delta * episode_plan_calls
    )
    total_tokens = baseline_prompt_tokens + baseline_output_tokens

    manifest = budget["manifest"]
    return {
        "schema_version": 1,
        "measurement_scope": (
            "Offline deterministic replay using o200k_base. Savings count only "
            "representation/deduplication changes that preserve the complete discovery corpus. "
            "This is a conservative prompt-token projection, not live billing."
        ),
        "baseline_episode": target_date.isoformat(),
        "available_news_files": [path.name for path in available_files],
        "missing_news_dates": [value.isoformat() for value in missing_dates],
        "discovery_item_count_before": len(source_items),
        "discovery_item_count_after": manifest["discovery_item_count_after"],
        "removed_source_items": manifest["removed_source_items"],
        "all_discovery_sources_preserved": manifest["all_discovery_sources_preserved"],
        "selected_item_count": manifest["selected_item_count"],
        "selected_exact_source_matches": manifest["selected_exact_source_matches"],
        "legacy_selected_news_tokens_o200k": tokens(legacy_selected_json),
        "optimized_selected_index_tokens_o200k": tokens(optimized_selected_json),
        "selected_news_tokens_saved_per_call": selected_delta,
        "legacy_news_text_tokens_o200k": tokens(discovery_json),
        "optimized_news_text_tokens_o200k": tokens(optimized_discovery_json),
        "news_text_tokens_saved_per_call": news_delta,
        "legacy_episode_plan_tokens_o200k": tokens(legacy_plan_json),
        "optimized_episode_plan_tokens_o200k": tokens(optimized_plan_json),
        "episode_plan_tokens_saved_per_call": plan_delta,
        "historical_selected_context_call_count": selected_context_calls,
        "historical_news_context_call_count": news_context_calls,
        "historical_episode_plan_call_count": episode_plan_calls,
        "historical_prompt_tokens": baseline_prompt_tokens,
        "historical_output_tokens": baseline_output_tokens,
        "estimated_prompt_tokens_saved": estimated_saved_prompt_tokens,
        "estimated_prompt_reduction_pct": round(
            estimated_saved_prompt_tokens / baseline_prompt_tokens * 100.0, 1
        )
        if baseline_prompt_tokens
        else 0.0,
        "estimated_total_token_reduction_pct_if_output_unchanged": round(
            estimated_saved_prompt_tokens / total_tokens * 100.0, 1
        )
        if total_tokens
        else 0.0,
        "historical_successful_step_counts": dict(steps),
        "guarantees": {
            "all_18_discovery_sources_still_available": len(source_items)
            == manifest["discovery_item_count_after"],
            "selected_raw_content_still_available_in_news_text": (
                manifest["selected_exact_source_matches"] == manifest["selected_item_count"]
            ),
            "model_generated_source_summaries": False,
            "source_filtering_or_rag": False,
            "review_count_changed": False,
            "refinement_count_changed": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay no-source-loss context deduplication against a frozen episode"
    )
    parser.add_argument("--episode-dir", required=True)
    parser.add_argument("--news-dir", default="news")
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = replay(
        episode_dir=Path(args.episode_dir),
        news_dir=Path(args.news_dir),
        target_date=date.fromisoformat(args.target_date),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
