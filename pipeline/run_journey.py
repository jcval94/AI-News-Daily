from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.architecture_manifest import manifest


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _sum_usage(records: list[dict[str, Any]]) -> dict[str, int]:
    result = {"prompt_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "total_tokens": 0}
    for record in records:
        usage = record.get("usage", {}) if isinstance(record.get("usage"), dict) else {}
        for key in result:
            value = usage.get(key)
            if isinstance(value, int):
                result[key] += value
    if result["total_tokens"] == 0:
        result["total_tokens"] = result["prompt_tokens"] + result["output_tokens"] + result["reasoning_tokens"]
    return result


def _cost_by_step(snapshot: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    rows = snapshot.get("breakdown_by_step", []) if isinstance(snapshot, dict) else []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        step = str(row.get("step") or "")
        try:
            cost = float(row.get("estimated_cost_usd") or 0)
        except (TypeError, ValueError):
            cost = 0.0
        if step:
            result[step] = result.get(step, 0.0) + cost
    return result


def _elapsed(records: list[dict[str, Any]]) -> float:
    total = 0.0
    for record in records:
        try:
            total += float(record.get("elapsed_seconds") or 0)
        except (TypeError, ValueError):
            pass
    return round(total, 3)


def derive_run_journey(
    *,
    episode_dir: Path,
    media_dir: Path | None = None,
    cost_snapshot: dict[str, Any] | None = None,
    architecture: dict[str, Any] | None = None,
) -> dict[str, Any]:
    architecture = architecture or manifest()
    cost_snapshot = cost_snapshot or {}
    trace = _read_json(episode_dir / "execution_trace.json", {})
    run_state = _read_json(episode_dir / "run_state.json", {})
    selected = _read_json(episode_dir / "selected_news.json", {})
    novelty = _read_json(episode_dir / "novelty_check.json", {})
    reviews = _read_json(episode_dir / "reviews.json", {})
    report = _read_json(episode_dir / "run_report.json", {})
    plan = _read_json(episode_dir / "episode_plan.json", {})

    agent_calls = trace.get("agent_calls", []) if isinstance(trace, dict) else []
    agent_calls = [item for item in agent_calls if isinstance(item, dict)] if isinstance(agent_calls, list) else []
    refinement_iterations = trace.get("refinement_iterations", []) if isinstance(trace, dict) else []
    if not isinstance(refinement_iterations, list):
        refinement_iterations = []
    costs = _cost_by_step(cost_snapshot)

    final_status = str(run_state.get("status") or "unknown")
    reached_quality_gate = bool(reviews) or any(
        str(call.get("step") or "").endswith("_judge") for call in agent_calls
    )
    reached_plan = bool(plan)
    reached_selection = bool(selected)

    stages: list[dict[str, Any]] = []
    for stage in architecture.get("stages", []):
        if not isinstance(stage, dict):
            continue
        stage_id = str(stage.get("id") or "")
        trace_steps = [str(value) for value in stage.get("trace_steps", [])]
        matched = [call for call in agent_calls if str(call.get("step") or "") in trace_steps]
        usage = _sum_usage(matched)
        errors = sum(1 for call in matched if str(call.get("status") or "") == "error")
        successes = sum(1 for call in matched if str(call.get("status") or "") == "success")
        cost = sum(costs.get(step, 0.0) for step in trace_steps)

        if matched:
            status = "executed" if successes else "error"
        elif stage_id in {"trigger", "workspace", "ingest", "memory"} and (run_state or reached_selection):
            status = "inferred"
        elif stage_id == "novelty" and novelty:
            status = "executed"
        elif stage_id == "quality_gate" and reached_quality_gate:
            status = "executed"
        elif stage_id == "refinement_router" and reached_quality_gate:
            status = "executed" if any(item.get("next_refinement_phase") for item in refinement_iterations if isinstance(item, dict)) else "not_required"
        elif stage_id in {"factual_refine", "voice_refine", "secondary_refine"} and reached_quality_gate:
            status = "not_required"
        elif stage_id == "media_materialize" and media_dir is not None and (media_dir / "manifest.json").exists():
            status = "executed"
        elif stage_id == "report_promote" and (run_state or report):
            status = "executed" if final_status == "approved" else "terminal"
        elif stage_id == "pages":
            status = "current_view"
        elif stage_id == "planning" and reached_plan:
            status = "inferred"
        else:
            status = "not_reached"

        stages.append(
            {
                "id": stage_id,
                "title": stage.get("title"),
                "kind": stage.get("kind"),
                "status": status,
                "trace_steps": trace_steps,
                "attempts": len(matched),
                "successes": successes,
                "errors": errors,
                "tokens": usage["total_tokens"],
                "elapsed_seconds": _elapsed(matched),
                "estimated_cost_usd": round(cost, 8),
            }
        )

    selected_items = selected.get("items", []) if isinstance(selected, dict) else []
    novelty_attempts = novelty.get("attempts", []) if isinstance(novelty, dict) else []
    final_novelty = novelty_attempts[-1] if isinstance(novelty_attempts, list) and novelty_attempts else {}
    last_iteration = refinement_iterations[-1] if refinement_iterations else {}

    return {
        "status": final_status,
        "publishable": bool(run_state.get("publishable", final_status == "approved")),
        "reason": str(run_state.get("reason") or ""),
        "selected_news_count": len(selected_items) if isinstance(selected_items, list) else 0,
        "novelty_attempts": len(novelty_attempts) if isinstance(novelty_attempts, list) else 0,
        "nearest_similarity": final_novelty.get("similarity") if isinstance(final_novelty, dict) else None,
        "refinement_iterations": len(refinement_iterations),
        "last_next_refinement_phase": last_iteration.get("next_refinement_phase") if isinstance(last_iteration, dict) else None,
        "agent_call_attempts": len(agent_calls),
        "stages": stages,
    }
