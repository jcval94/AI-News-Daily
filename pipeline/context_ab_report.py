from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

_JUDGE_KEYS = (
    "editorial",
    "seo_master",
    "youtube_attention_master",
    "voice_humanity",
)
_RISK_RANK = {"low": 0, "medium": 1, "high": 2}


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _usage_summary(trace: dict[str, Any]) -> dict[str, Any]:
    totals = {
        "prompt_tokens": 0,
        "cached_prompt_tokens": 0,
        "uncached_prompt_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
    }
    cache_fields_seen = 0
    successful_calls = 0
    for call in trace.get("agent_calls", []) if isinstance(trace, dict) else []:
        if not isinstance(call, dict) or call.get("status") != "success":
            continue
        usage = call.get("usage") if isinstance(call.get("usage"), dict) else {}
        successful_calls += 1
        if "cached_prompt_tokens" in usage or "uncached_prompt_tokens" in usage:
            cache_fields_seen += 1
        for key in totals:
            value = usage.get(key)
            if isinstance(value, int):
                totals[key] += value
    totals["successful_calls"] = successful_calls
    totals["cache_telemetry_available"] = successful_calls > 0 and cache_fields_seen == successful_calls
    return totals


def summarize_episode(episode_dir: Path) -> dict[str, Any]:
    reviews = _load_json(episode_dir / "reviews.json", {})
    trace = _load_json(episode_dir / "execution_trace.json", {})
    selected = _load_json(episode_dir / "selected_news.json", {"items": []})
    budget = _load_json(episode_dir / "context_budget.json", {})
    run_state = _load_json(episode_dir / "run_state.json", {})

    judges: dict[str, dict[str, Any]] = {}
    for key in _JUDGE_KEYS:
        value = reviews.get(key) if isinstance(reviews, dict) else None
        if isinstance(value, dict):
            judges[key] = {
                "score": value.get("score"),
                "approved": value.get("approved"),
                "factuality_risk": value.get("factuality_risk"),
            }

    script_path = episode_dir / "script.txt"
    script = script_path.read_text(encoding="utf-8") if script_path.exists() else ""
    selected_items = selected.get("items", []) if isinstance(selected, dict) else []
    status = run_state.get("status") or run_state.get("outcome") or ("complete" if script else "missing")

    return {
        "episode_dir": str(episode_dir),
        "status": status,
        "script_exists": bool(script.strip()),
        "script_word_count": len(script.split()),
        "approved_for_multimedia": bool(reviews.get("approved_for_multimedia")) if isinstance(reviews, dict) else False,
        "selected_count": len(selected_items) if isinstance(selected_items, list) else 0,
        "judges": judges,
        "usage": _usage_summary(trace),
        "context_budget": budget,
    }


def compare_arms(
    control: dict[str, Any],
    candidate: dict[str, Any],
    *,
    quality_tolerance: float = 0.25,
    min_prompt_reduction_pct: float = 5.0,
) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []

    if not control.get("script_exists"):
        failures.append("control_script_missing")
    if not candidate.get("script_exists"):
        failures.append("candidate_script_missing")

    if control.get("approved_for_multimedia") and not candidate.get("approved_for_multimedia"):
        failures.append("candidate_lost_multimedia_approval")

    score_deltas: dict[str, float] = {}
    for key in _JUDGE_KEYS:
        control_judge = control.get("judges", {}).get(key, {})
        candidate_judge = candidate.get("judges", {}).get(key, {})
        c_score = control_judge.get("score")
        n_score = candidate_judge.get("score")
        if isinstance(c_score, (int, float)) and isinstance(n_score, (int, float)):
            delta = round(float(n_score) - float(c_score), 4)
            score_deltas[key] = delta
            if delta < -quality_tolerance:
                failures.append(f"judge_regression:{key}:{delta}")
        elif key in control.get("judges", {}) or key in candidate.get("judges", {}):
            warnings.append(f"judge_score_missing:{key}")

    control_risk = str(control.get("judges", {}).get("editorial", {}).get("factuality_risk") or "").lower()
    candidate_risk = str(candidate.get("judges", {}).get("editorial", {}).get("factuality_risk") or "").lower()
    if control_risk in _RISK_RANK and candidate_risk in _RISK_RANK:
        if _RISK_RANK[candidate_risk] > _RISK_RANK[control_risk]:
            failures.append(f"factuality_risk_regression:{control_risk}->{candidate_risk}")
    else:
        warnings.append("factuality_risk_not_comparable")

    budget = candidate.get("context_budget") if isinstance(candidate.get("context_budget"), dict) else {}
    if not budget:
        failures.append("candidate_context_budget_manifest_missing")
    else:
        if budget.get("all_discovery_sources_preserved") is not True:
            failures.append("candidate_discovery_source_loss")
        if int(budget.get("removed_source_items", -1) or 0) != 0:
            failures.append("candidate_removed_source_items")
        selected_count = budget.get("selected_item_count")
        exact_count = budget.get("selected_exact_source_matches")
        if isinstance(selected_count, int) and isinstance(exact_count, int) and exact_count != selected_count:
            failures.append("candidate_selected_source_integrity_mismatch")

    control_usage = control.get("usage", {})
    candidate_usage = candidate.get("usage", {})
    control_prompt = int(control_usage.get("prompt_tokens", 0) or 0)
    candidate_prompt = int(candidate_usage.get("prompt_tokens", 0) or 0)
    prompt_saved = control_prompt - candidate_prompt
    prompt_reduction_pct = round((prompt_saved / control_prompt) * 100.0, 2) if control_prompt > 0 else 0.0
    if control_prompt <= 0 or candidate_prompt <= 0:
        failures.append("prompt_usage_missing")
    elif prompt_reduction_pct < min_prompt_reduction_pct:
        failures.append(f"prompt_reduction_below_floor:{prompt_reduction_pct}")

    cache_telemetry_complete = bool(control_usage.get("cache_telemetry_available")) and bool(candidate_usage.get("cache_telemetry_available"))
    if not cache_telemetry_complete:
        failures.append("cached_uncached_input_telemetry_incomplete")

    control_uncached = int(control_usage.get("uncached_prompt_tokens", 0) or 0)
    candidate_uncached = int(candidate_usage.get("uncached_prompt_tokens", 0) or 0)
    uncached_saved = control_uncached - candidate_uncached
    uncached_reduction_pct = round((uncached_saved / control_uncached) * 100.0, 2) if control_uncached > 0 else None

    return {
        "gate_pass": not failures,
        "quality_tolerance": quality_tolerance,
        "min_prompt_reduction_pct": min_prompt_reduction_pct,
        "failures": failures,
        "warnings": warnings,
        "judge_score_deltas": score_deltas,
        "factuality_risk": {"control": control_risk or None, "candidate": candidate_risk or None},
        "prompt_tokens": {
            "control": control_prompt,
            "candidate": candidate_prompt,
            "saved": prompt_saved,
            "reduction_pct": prompt_reduction_pct,
        },
        "uncached_prompt_tokens": {
            "control": control_uncached,
            "candidate": candidate_uncached,
            "saved": uncached_saved,
            "reduction_pct": uncached_reduction_pct,
        },
        "cache_telemetry_complete": cache_telemetry_complete,
    }


def build_report(
    *,
    control_dir: Path,
    candidate_dir: Path,
    quality_tolerance: float = 0.25,
    min_prompt_reduction_pct: float = 5.0,
) -> dict[str, Any]:
    control = summarize_episode(control_dir)
    candidate = summarize_episode(candidate_dir)
    comparison = compare_arms(
        control,
        candidate,
        quality_tolerance=quality_tolerance,
        min_prompt_reduction_pct=min_prompt_reduction_pct,
    )
    return {"schema_version": 1, "control": control, "candidate": candidate, "comparison": comparison}


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare control vs no-source-loss context-budget runs")
    parser.add_argument("--control-dir", required=True)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--quality-tolerance", type=float, default=0.25)
    parser.add_argument("--min-prompt-reduction-pct", type=float, default=5.0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    report = build_report(
        control_dir=Path(args.control_dir),
        candidate_dir=Path(args.candidate_dir),
        quality_tolerance=args.quality_tolerance,
        min_prompt_reduction_pct=args.min_prompt_reduction_pct,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["comparison"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
