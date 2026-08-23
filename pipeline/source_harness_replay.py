from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import tiktoken

from pipeline.run import collect_available_news
from pipeline.source_harness import build_source_harness


def _exact_match(selected: dict[str, Any], source: dict[str, Any]) -> dict[str, bool]:
    return {
        "raw_content_exact_match": bool(source)
        and selected.get("raw_content") == source.get("raw_content"),
        "source_locator_exact_match": bool(source)
        and selected.get("source_locator") == source.get("source_locator"),
        "url_exact_match": bool(source) and selected.get("url") == source.get("url"),
    }


def replay(
    *, episode_dir: Path, news_dir: Path, target_date: date
) -> dict[str, Any]:
    selection = json.loads(
        (episode_dir / "selected_news.json").read_text(encoding="utf-8")
    )
    trace = json.loads(
        (episode_dir / "execution_trace.json").read_text(encoding="utf-8")
    )
    selected_items = selection.get("items", []) if isinstance(selection, dict) else []
    if not isinstance(selected_items, list) or not selected_items:
        raise ValueError("Historical episode has no selected news")

    discovery_json, available_files, missing_dates, source_items = collect_available_news(
        news_dir, target_date
    )
    source_by_id = {item.news_id: item.model_dump() for item in source_items}

    integrity: list[dict[str, Any]] = []
    for index, selected in enumerate(selected_items, start=1):
        if not isinstance(selected, dict):
            raise ValueError("selected_news contains a non-object item")
        source = source_by_id.get(str(selected.get("news_id", "")), {})
        row = {
            "selected_news_index": index,
            "news_id": selected.get("news_id"),
            **_exact_match(selected, source),
        }
        integrity.append(row)
    if not all(
        row["raw_content_exact_match"]
        and row["source_locator_exact_match"]
        and row["url_exact_match"]
        for row in integrity
    ):
        raise ValueError("Source integrity failed; refusing to estimate savings")

    harness = build_source_harness(
        selection,
        discovery_item_count=len(source_items),
        discovery_context_chars=len(discovery_json),
    )

    enc = tiktoken.get_encoding("o200k_base")

    def tokens(value: Any) -> int:
        return len(enc.encode(str(value or "")))

    full_selected_json = json.dumps(selection, ensure_ascii=False)
    legacy_combined_tokens = tokens(full_selected_json) + tokens(discovery_json)
    harness_combined_tokens = tokens(harness["selected_news_json"]) + tokens(
        harness["news_text_json"]
    )
    full_selected_tokens = tokens(full_selected_json)
    harness_index_tokens = tokens(harness["selected_news_json"])

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

    # These agents explicitly interpolate both selected_news and news_text today.
    full_source_calls = (
        steps["plan_episode"]
        + steps["replan_episode_novelty"]
        + steps["write_script"]
        + steps["editorial_judge"]
        + steps["refine_script"]
    )
    # SEO interpolates selected_news but not news_text.
    seo_calls = steps["seo_judge"]

    estimated_saved_prompt_tokens = (
        (legacy_combined_tokens - harness_combined_tokens) * full_source_calls
        + (full_selected_tokens - harness_index_tokens) * seo_calls
    )
    total_tokens = baseline_prompt_tokens + baseline_output_tokens

    return {
        "schema_version": 1,
        "measurement_scope": (
            "Offline deterministic replay. o200k_base counts only the source-state payloads; "
            "E2E savings are projected onto historical call counts and are not live billing."
        ),
        "baseline_episode": target_date.isoformat(),
        "discovery_item_count": len(source_items),
        "selected_item_count": len(selected_items),
        "omitted_after_selector_count": max(0, len(source_items) - len(selected_items)),
        "available_news_files": [path.name for path in available_files],
        "missing_news_dates": [value.isoformat() for value in missing_dates],
        "selected_source_integrity": integrity,
        "legacy_source_state_tokens_o200k": legacy_combined_tokens,
        "harness_source_state_tokens_o200k": harness_combined_tokens,
        "source_state_reduction_pct": round(
            (1.0 - harness_combined_tokens / legacy_combined_tokens) * 100.0, 1
        ),
        "legacy_selected_news_tokens_o200k": full_selected_tokens,
        "harness_selected_index_tokens_o200k": harness_index_tokens,
        "historical_full_source_call_count": full_source_calls,
        "historical_seo_call_count": seo_calls,
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
        "harness_manifest": harness["manifest"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay progressive source disclosure against a frozen episode"
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
