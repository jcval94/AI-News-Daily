from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import tiktoken

from pipeline.evidence_reconciliation import reconcile_evidence_indices
from pipeline.run import collect_available_news
from pipeline.run_cost_optimized import compact_agent_state


def _exact_source_match(
    selected_item: dict[str, Any], source_item: dict[str, Any]
) -> dict[str, bool]:
    return {
        "raw_content_exact_match": bool(source_item)
        and source_item.get("raw_content") == selected_item.get("raw_content"),
        "source_locator_exact_match": bool(source_item)
        and source_item.get("source_locator") == selected_item.get("source_locator"),
        "url_exact_match": bool(source_item)
        and source_item.get("url") == selected_item.get("url"),
    }


def _all_exact(rows: list[dict[str, Any]]) -> bool:
    return bool(rows) and all(
        bool(row.get("raw_content_exact_match"))
        and bool(row.get("source_locator_exact_match"))
        and bool(row.get("url_exact_match"))
        for row in rows
    )


def replay_cost_context(
    *,
    episode_dir: Path,
    news_dir: Path,
    target_date: date,
) -> dict[str, Any]:
    selection = json.loads(
        (episode_dir / "selected_news.json").read_text(encoding="utf-8")
    )
    plan = json.loads((episode_dir / "episode_plan.json").read_text(encoding="utf-8"))
    historical_trace = json.loads(
        (episode_dir / "execution_trace.json").read_text(encoding="utf-8")
    )

    news_text, available_files, missing_dates, source_items = collect_available_news(
        news_dir, target_date
    )
    state = {
        "selected_news": json.dumps(selection, ensure_ascii=False),
        "news_text": news_text,
        "episode_plan": json.dumps(plan, ensure_ascii=False),
        "draft_script": (episode_dir / "script.txt").read_text(encoding="utf-8"),
    }

    selected_items = selection.get("items", []) if isinstance(selection, dict) else []
    if not isinstance(selected_items, list) or not selected_items:
        raise ValueError("Historical artifact contains no selected news")

    reconciled, changes = reconcile_evidence_indices(plan, selection)
    declared_indices = {
        item["evidence_id"]: item["selected_news_index"]
        for item in plan.get("evidence", [])
    }
    reconciled_indices = {
        item["evidence_id"]: item["selected_news_index"]
        for item in reconciled.get("evidence", [])
    }

    source_by_id = {item.news_id: item.model_dump() for item in source_items}

    # Conservative mode promises exact factual source text for every selected story,
    # not just for the subset used as planned evidence. Validate that promise first.
    selected_source_integrity: list[dict[str, Any]] = []
    for index, selected_item in enumerate(selected_items, start=1):
        if not isinstance(selected_item, dict):
            raise ValueError("selected_news contains a non-object item")
        source_item = source_by_id.get(str(selected_item.get("news_id", "")), {})
        selected_source_integrity.append(
            {
                "selected_news_index": index,
                "news_id": selected_item.get("news_id"),
                **_exact_source_match(selected_item, source_item),
            }
        )
    if not _all_exact(selected_source_integrity):
        raise ValueError(
            "Selected-news source integrity failed; refusing to report context savings"
        )

    evidence_integrity: list[dict[str, Any]] = []
    for evidence in reconciled.get("evidence", []):
        index = int(evidence["selected_news_index"])
        selected_item = selected_items[index - 1]
        source_item = source_by_id.get(str(selected_item.get("news_id", "")), {})
        evidence_integrity.append(
            {
                "evidence_id": evidence["evidence_id"],
                "selected_news_index": index,
                "news_id": selected_item.get("news_id"),
                **_exact_source_match(selected_item, source_item),
            }
        )
    if not _all_exact(evidence_integrity):
        raise ValueError(
            "Reconciled evidence integrity failed; refusing to report context savings"
        )

    enc = tiktoken.get_encoding("o200k_base")

    def tok(text: Any) -> int:
        return len(enc.encode(str(text or "")))

    selected_full_tokens = tok(state["selected_news"])
    news_full_tokens = tok(state["news_text"])
    source_full_tokens = selected_full_tokens + news_full_tokens

    successful_calls = [
        call
        for call in historical_trace.get("agent_calls", [])
        if isinstance(call, dict) and call.get("status") == "success"
    ]
    successful_steps = Counter(call.get("step") for call in successful_calls)
    baseline_prompt_tokens = sum(
        int((call.get("usage") or {}).get("prompt_tokens", 0) or 0)
        for call in successful_calls
    )
    baseline_output_tokens = sum(
        int((call.get("usage") or {}).get("output_tokens", 0) or 0)
        for call in successful_calls
    )
    factual_calls = (
        successful_steps["write_script"]
        + successful_steps["editorial_judge"]
        + successful_steps["refine_script"]
    )
    seo_calls = successful_steps["seo_judge"]

    variants: dict[str, Any] = {}
    for mode in ("conservative", "strict"):
        factual_state, factual_stats = compact_agent_state(
            SimpleNamespace(name="script_critic"), state, mode=mode
        )
        seo_state, seo_stats = compact_agent_state(
            SimpleNamespace(name="seo_master"), state, mode=mode
        )
        if factual_stats is None or seo_stats is None:
            raise ValueError(f"{mode} compaction unexpectedly failed open")

        expected_raw_sources = (
            len(selected_items)
            if mode == "conservative"
            else len(set(reconciled_indices.values()))
        )
        if factual_stats.get("raw_source_item_count") != expected_raw_sources:
            raise ValueError(
                f"{mode} retained {factual_stats.get('raw_source_item_count')} raw sources; "
                f"expected {expected_raw_sources}"
            )

        factual_source_tokens = tok(factual_state["selected_news"]) + tok(
            factual_state["news_text"]
        )
        seo_selected_tokens = tok(seo_state["selected_news"])
        estimated_saved_prompt_tokens = (
            (source_full_tokens - factual_source_tokens) * factual_calls
            + (selected_full_tokens - seo_selected_tokens) * seo_calls
        )
        baseline_total = baseline_prompt_tokens + baseline_output_tokens
        variants[mode] = {
            "source_context_chars_before": len(state["selected_news"])
            + len(state["news_text"]),
            "source_context_chars_after": factual_stats["context_chars_after"],
            "source_context_char_reduction_pct": factual_stats[
                "context_char_reduction_pct"
            ],
            "source_context_tokens_before_o200k": source_full_tokens,
            "source_context_tokens_after_o200k": factual_source_tokens,
            "source_context_token_reduction_pct": round(
                (1 - factual_source_tokens / source_full_tokens) * 100, 1
            ),
            "seo_selected_tokens_before_o200k": selected_full_tokens,
            "seo_selected_tokens_after_o200k": seo_selected_tokens,
            "historical_factual_call_count": factual_calls,
            "historical_seo_call_count": seo_calls,
            "raw_source_item_count": factual_stats.get("raw_source_item_count"),
            "estimated_prompt_tokens_saved_static_replay": estimated_saved_prompt_tokens,
            "estimated_baseline_prompt_reduction_pct_static_replay": round(
                estimated_saved_prompt_tokens / baseline_prompt_tokens * 100, 1
            )
            if baseline_prompt_tokens
            else 0.0,
            "estimated_total_token_reduction_pct_if_output_unchanged": round(
                estimated_saved_prompt_tokens / baseline_total * 100, 1
            )
            if baseline_total
            else 0.0,
            "used_evidence_indices": factual_stats["used_evidence_indices"],
        }

    return {
        "schema_version": 3,
        "measurement_scope": (
            "Offline deterministic replay of source-context payload only. Token estimates "
            "use o200k_base and are not measured API billing/usage."
        ),
        "baseline_run_id": 32541706631,
        "target_date": target_date.isoformat(),
        "available_news_files": [path.name for path in available_files],
        "missing_news_dates": [value.isoformat() for value in missing_dates],
        "source_item_count": len(source_items),
        "selected_item_count": len(selected_items),
        "selected_source_integrity": selected_source_integrity,
        "declared_evidence_indices": declared_indices,
        "reconciled_evidence_indices": reconciled_indices,
        "evidence_reconciliation_changes": changes,
        "evidence_integrity": evidence_integrity,
        "historical_baseline_prompt_tokens": baseline_prompt_tokens,
        "historical_baseline_output_tokens": baseline_output_tokens,
        "historical_successful_step_counts": dict(successful_steps),
        "variants": variants,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay AI-News context reduction against a frozen historical artifact"
    )
    parser.add_argument("--episode-dir", required=True)
    parser.add_argument("--news-dir", default="news")
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target = date.fromisoformat(args.target_date)
    report = replay_cost_context(
        episode_dir=Path(args.episode_dir),
        news_dir=Path(args.news_dir),
        target_date=target,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
