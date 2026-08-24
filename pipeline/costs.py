from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _tree_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for item in path.rglob("*"):
        if not item.is_file():
            continue
        try:
            total += item.stat().st_size
        except OSError:
            continue
    return total


def _model_from_report(report: dict[str, Any], fallback: str) -> str:
    configuration = report.get("configuration", {}) if isinstance(report, dict) else {}
    model = configuration.get("openai_model") if isinstance(configuration, dict) else None
    return str(model or fallback or "").strip()


def _model_rate(pricing: dict[str, Any], model: str) -> dict[str, Any] | None:
    models = pricing.get("models", {}) if isinstance(pricing, dict) else {}
    rate = models.get(model) if isinstance(models, dict) else None
    return rate if isinstance(rate, dict) else None


def _billable_usage(usage: dict[str, Any]) -> dict[str, int]:
    prompt = _int(usage.get("prompt_tokens"))
    output = _int(usage.get("output_tokens"))
    reasoning = _int(usage.get("reasoning_tokens"))
    total = _int(usage.get("total_tokens"))
    # Some adapters expose reasoning separately from candidate/output tokens, while others
    # include it in the aggregate. Use the larger observed output-side count without double billing.
    output_side_from_total = max(0, total - prompt) if total else 0
    billable_output = max(output + reasoning, output_side_from_total, output)
    return {
        "prompt_tokens": prompt,
        "output_tokens": output,
        "reasoning_tokens": reasoning,
        "total_tokens": total or (prompt + output + reasoning),
        "billable_output_tokens": billable_output,
    }


def _estimate_call_cost(usage: dict[str, Any], rate: dict[str, Any] | None) -> float | None:
    if not rate:
        return None
    normalized = _billable_usage(usage)
    input_rate = _number(rate.get("input_per_million"))
    output_rate = _number(rate.get("output_per_million"))
    if input_rate is None or output_rate is None:
        return None
    # Cached-input token counts are not persisted by the current trace. Conservatively treat
    # all prompt tokens as standard input rather than claiming an unobserved cache discount.
    return round(
        (normalized["prompt_tokens"] / 1_000_000.0) * input_rate
        + (normalized["billable_output_tokens"] / 1_000_000.0) * output_rate,
        8,
    )


def _trace_rows(
    trace: dict[str, Any],
    *,
    scope: str,
    model: str,
    rate: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    calls = trace.get("agent_calls", []) if isinstance(trace, dict) else []
    if not isinstance(calls, list):
        calls = []
    for index, call in enumerate(calls, start=1):
        if not isinstance(call, dict):
            continue
        usage = call.get("usage", {}) if isinstance(call.get("usage"), dict) else {}
        normalized = _billable_usage(usage)
        observed_usage = any(normalized[key] > 0 for key in ("prompt_tokens", "output_tokens", "reasoning_tokens", "total_tokens"))
        status = str(call.get("status") or "unknown")
        estimated = _estimate_call_cost(usage, rate) if observed_usage else None
        if status == "error" and not observed_usage:
            warnings.append(
                f"{scope}:{call.get('step') or 'unknown'} attempt {call.get('attempt') or 1} failed without persisted token usage; any provider charge is not measurable from this historical trace."
            )
        rows.append(
            {
                "scope": scope,
                "sequence": index,
                "step": str(call.get("step") or "unknown"),
                "agent": str(call.get("agent") or "unknown"),
                "iteration": call.get("iteration"),
                "attempt": _int(call.get("attempt")) or 1,
                "status": status,
                "elapsed_seconds": _number(call.get("elapsed_seconds")),
                "model": model,
                **normalized,
                "usage_observed": observed_usage,
                "estimated_cost_usd": estimated,
                "error_type": call.get("error_type"),
            }
        )
    return rows, warnings


def _aggregate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("scope")), str(row.get("step")), str(row.get("agent")))
        if key not in groups:
            groups[key] = {
                "scope": key[0],
                "step": key[1],
                "agent": key[2],
                "attempts": 0,
                "errors": 0,
                "prompt_tokens": 0,
                "output_tokens": 0,
                "reasoning_tokens": 0,
                "billable_output_tokens": 0,
                "total_tokens": 0,
                "elapsed_seconds": 0.0,
                "estimated_cost_usd": 0.0,
                "unpriced_attempts": 0,
            }
        group = groups[key]
        group["attempts"] += 1
        if row.get("status") == "error":
            group["errors"] += 1
        for token_key in ("prompt_tokens", "output_tokens", "reasoning_tokens", "billable_output_tokens", "total_tokens"):
            group[token_key] += _int(row.get(token_key))
        group["elapsed_seconds"] += float(row.get("elapsed_seconds") or 0.0)
        cost = row.get("estimated_cost_usd")
        if cost is None and row.get("usage_observed"):
            group["unpriced_attempts"] += 1
        elif cost is not None:
            group["estimated_cost_usd"] += float(cost)
    result = list(groups.values())
    for group in result:
        group["elapsed_seconds"] = round(group["elapsed_seconds"], 3)
        group["estimated_cost_usd"] = round(group["estimated_cost_usd"], 8)
    result.sort(key=lambda item: (item["scope"], -item["estimated_cost_usd"], item["step"]))
    return result


def _provider_counts(manifest: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for item in manifest:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider") or "unknown").strip().lower()
        counts[provider] += 1
    return dict(sorted(counts.items()))


def build_cost_snapshot(
    *,
    episode_dir: Path,
    media_dir: Path,
    media_zip: Path,
    output_dir: Path,
    pricing_path: Path = Path("config/cost_rates.json"),
    episode_budget_usd: float | None = None,
) -> dict[str, Any]:
    pricing = read_json(pricing_path, {})
    report = read_json(episode_dir / "run_report.json", {})
    production_trace = read_json(episode_dir / "execution_trace.json", {})
    media_plan = read_json(media_dir / "plan.json", {})
    manifest_raw = read_json(media_dir / "manifest.json", [])
    manifest = manifest_raw if isinstance(manifest_raw, list) else []

    fallback_model = os.getenv("OPENAI_MODEL", "gpt-5.4-nano")
    production_model = _model_from_report(report if isinstance(report, dict) else {}, fallback_model)
    review_model = str(os.getenv("OPENAI_MODEL") or production_model or fallback_model)
    production_rate = _model_rate(pricing, production_model)
    review_rate = _model_rate(pricing, review_model)

    production_rows, warnings = _trace_rows(
        production_trace if isinstance(production_trace, dict) else {},
        scope="production_pipeline",
        model=production_model,
        rate=production_rate,
    )
    review_trace = {
        "agent_calls": media_plan.get("agent_trace", []) if isinstance(media_plan, dict) else []
    }
    review_rows, review_warnings = _trace_rows(
        review_trace,
        scope="review_media_planner",
        model=review_model,
        rate=review_rate,
    )
    warnings.extend(review_warnings)
    rows = production_rows + review_rows

    known_openai_cost = round(
        sum(float(row["estimated_cost_usd"]) for row in rows if row.get("estimated_cost_usd") is not None),
        8,
    )
    observed_prompt = sum(_int(row.get("prompt_tokens")) for row in rows)
    observed_output = sum(_int(row.get("output_tokens")) for row in rows)
    observed_reasoning = sum(_int(row.get("reasoning_tokens")) for row in rows)
    observed_total = sum(_int(row.get("total_tokens")) for row in rows)
    observed_calls = sum(1 for row in rows if row.get("usage_observed"))
    unmeasured_failed_attempts = sum(
        1 for row in rows if row.get("status") == "error" and not row.get("usage_observed")
    )
    unpriced_observed_attempts = sum(
        1 for row in rows if row.get("usage_observed") and row.get("estimated_cost_usd") is None
    )

    providers = _provider_counts(manifest)
    pexels_assets = providers.get("pexels", 0)
    generated_assets = providers.get("generated_fallback", 0)

    services = pricing.get("services", {}) if isinstance(pricing, dict) else {}
    pexels_rate = services.get("pexels", {}) if isinstance(services, dict) else {}
    actions_rate = services.get("github_actions_standard_public_runner", {}) if isinstance(services, dict) else {}
    storage_rate = services.get("github_actions_artifact_storage", {}) if isinstance(services, dict) else {}
    pexels_known_cost = 0.0 if _number(pexels_rate.get("usd_per_request")) == 0 else None
    actions_compute_cost = 0.0 if _number(actions_rate.get("usd_per_minute")) == 0 else None

    media_bytes = _tree_bytes(media_dir)
    zip_bytes = _tree_bytes(media_zip)
    site_bytes_before_snapshot = _tree_bytes(output_dir)
    raw_upload_bytes = media_bytes + zip_bytes + site_bytes_before_snapshot
    storage_gb = raw_upload_bytes / (1024**3)
    retention_days = 30
    storage_rate_value = _number(storage_rate.get("usd_per_gb_month_over_included_allowance"))
    gross_storage_exposure = (
        round(storage_gb * (retention_days / 30.0) * storage_rate_value, 8)
        if storage_rate_value is not None
        else None
    )

    known_direct_cost = known_openai_cost
    if pexels_known_cost is not None:
        known_direct_cost += pexels_known_cost
    if actions_compute_cost is not None:
        known_direct_cost += actions_compute_cost
    known_direct_cost = round(known_direct_cost, 8)

    if episode_budget_usd is None:
        env_budget = _number(os.getenv("REVIEW_HUB_EPISODE_BUDGET_USD"))
        episode_budget_usd = env_budget if env_budget is not None and env_budget >= 0 else None
    remaining = (
        round(float(episode_budget_usd) - known_direct_cost, 8)
        if episode_budget_usd is not None
        else None
    )
    utilization = (
        round((known_direct_cost / float(episode_budget_usd)) * 100.0, 2)
        if episode_budget_usd not in (None, 0)
        else None
    )

    if production_rate is None:
        warnings.append(f"No pricing snapshot found for production model {production_model}; observed production tokens are unpriced.")
    if review_rows and review_rate is None:
        warnings.append(f"No pricing snapshot found for review planner model {review_model}; observed review-planner tokens are unpriced.")
    if unmeasured_failed_attempts:
        warnings.append(
            f"{unmeasured_failed_attempts} failed model attempt(s) have no persisted token usage; known cost is a lower bound for this historical run."
        )
    if unpriced_observed_attempts:
        warnings.append(
            f"{unpriced_observed_attempts} attempt(s) have observed tokens but no matching model price; they are excluded from the known direct cost."
        )

    return {
        "schema_version": 1,
        "currency": str(pricing.get("currency") or "USD"),
        "pricing_snapshot": {
            "as_of": pricing.get("as_of"),
            "path": str(pricing_path),
            "production_model": production_model,
            "review_model": review_model,
            "production_rate": production_rate,
            "review_rate": review_rate,
        },
        "budget": {
            "configured_usd": episode_budget_usd,
            "known_direct_cost_usd": known_direct_cost,
            "remaining_usd": remaining,
            "utilization_pct": utilization,
            "status": (
                "not_configured"
                if episode_budget_usd is None
                else "over_budget"
                if remaining is not None and remaining < 0
                else "within_budget"
            ),
        },
        "totals": {
            "known_openai_cost_usd": known_openai_cost,
            "pexels_known_cost_usd": pexels_known_cost,
            "github_actions_compute_known_cost_usd": actions_compute_cost,
            "known_direct_cost_usd": known_direct_cost,
            "artifact_storage_gross_exposure_usd": gross_storage_exposure,
            "artifact_storage_included_in_direct_total": False,
        },
        "usage": {
            "prompt_tokens": observed_prompt,
            "output_tokens": observed_output,
            "reasoning_tokens": observed_reasoning,
            "total_tokens": observed_total,
            "attempts_with_observed_usage": observed_calls,
            "unmeasured_failed_attempts": unmeasured_failed_attempts,
            "unpriced_observed_attempts": unpriced_observed_attempts,
        },
        "breakdown_by_step": _aggregate_rows(rows),
        "attempts": rows,
        "multimedia": {
            "asset_count": len(manifest),
            "provider_counts": providers,
            "pexels_assets": pexels_assets,
            "generated_fallback_assets": generated_assets,
            "media_directory_bytes": media_bytes,
            "media_zip_bytes": zip_bytes,
        },
        "github": {
            "repository_visibility_assumption": "public",
            "runner_assumption": "standard GitHub-hosted runner",
            "compute_cost_policy_usd": actions_compute_cost,
            "review_site_bytes_before_cost_snapshot": site_bytes_before_snapshot,
            "raw_artifact_upload_bytes_estimate": raw_upload_bytes,
            "artifact_retention_days": retention_days,
            "artifact_storage_rate_usd_per_gb_month_over_allowance": storage_rate_value,
            "artifact_storage_gross_exposure_usd": gross_storage_exposure,
            "artifact_storage_note": "Gross exposure assumes the entire raw upload footprint were billable for 30 days. Actual billing depends on compression, account plan, shared included storage, other artifacts/packages, and account-level metered usage; that billing state is not available inside this artifact.",
        },
        "coverage": {
            "known_direct_total_is_complete": unmeasured_failed_attempts == 0 and unpriced_observed_attempts == 0,
            "cached_input_discount_measured": False,
            "pexels_request_count_measured": False,
            "github_account_billing_measured": False,
            "warnings": warnings,
        },
        "sources": {
            "openai": production_rate.get("source") if isinstance(production_rate, dict) else None,
            "pexels": pexels_rate.get("source") if isinstance(pexels_rate, dict) else None,
            "github_actions": actions_rate.get("source") if isinstance(actions_rate, dict) else None,
            "github_storage": storage_rate.get("source") if isinstance(storage_rate, dict) else None,
        },
    }
