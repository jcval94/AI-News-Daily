"""Aggregate gates for semantic multimedia stress runs."""
from __future__ import annotations

from typing import Any

from .models import ExperimentProfile


def evaluate_scorecard(profile: ExperimentProfile, run: dict[str, Any]) -> dict[str, Any]:
    case_results = list(run.get("case_results") or [])
    attempts = int((run.get("summary") or {}).get("attempts") or 0)
    passes = int((run.get("summary") or {}).get("overall_passes") or 0)
    overall_pass_rate = passes / attempts if attempts else 0.0
    minimum_case_pass_rate = min(
        (float(item.get("pass_rate") or 0.0) for item in case_results),
        default=0.0,
    )
    stable_cases = sum(bool(item.get("stable")) for item in case_results)
    errors = sum(int(item.get("errors") or 0) for item in case_results)

    hard_failures: list[dict[str, Any]] = []
    failed_cases: set[str] = set()

    for item in case_results:
        case_id = str(item.get("case_id") or "")
        if float(item.get("pass_rate") or 0.0) < profile.thresholds.min_case_pass_rate:
            failed_cases.add(case_id)
        if profile.thresholds.require_identity_stability and not bool(item.get("stable")):
            failed_cases.add(case_id)

        for row in item.get("runs") or []:
            repetition = int(row.get("repetition") or 0)
            if row.get("error"):
                hard_failures.append({
                    "case_id": case_id,
                    "repetition": repetition,
                    "source": "runtime",
                    "code": "runtime_error",
                    "detail": str(row["error"])[:1000],
                })
                failed_cases.add(case_id)

            deterministic = row.get("deterministic") or {}
            checks = deterministic.get("checks") or {}
            for check in profile.thresholds.hard_fail_checks:
                if check in checks and not bool(checks[check]):
                    hard_failures.append({
                        "case_id": case_id,
                        "repetition": repetition,
                        "source": "deterministic",
                        "code": check,
                        "detail": f"Deterministic check {check} failed.",
                    })
                    failed_cases.add(case_id)

            critic = row.get("critic") or {}
            for code in critic.get("failure_codes") or []:
                if code in profile.thresholds.hard_fail_critic_codes:
                    hard_failures.append({
                        "case_id": case_id,
                        "repetition": repetition,
                        "source": "critic",
                        "code": str(code),
                        "detail": str(critic.get("summary") or code)[:1000],
                    })
                    failed_cases.add(case_id)

    threshold_fail = (
        overall_pass_rate < profile.thresholds.min_overall_pass_rate
        or minimum_case_pass_rate < profile.thresholds.min_case_pass_rate
        or errors > profile.thresholds.max_errors
        or (
            profile.thresholds.require_identity_stability
            and stable_cases != len(case_results)
        )
        or bool(hard_failures)
    )

    return {
        "schema_version": 1,
        "profile_id": profile.id,
        "run_id": str(run.get("run_id") or ""),
        "verdict": "fail" if threshold_fail else "pass",
        "metrics": {
            "overall_pass_rate": round(overall_pass_rate, 6),
            "minimum_case_pass_rate": round(minimum_case_pass_rate, 6),
            "stable_cases": stable_cases,
            "total_cases": len(case_results),
            "errors": errors,
            "hard_fail_count": len(hard_failures),
        },
        "hard_failures": hard_failures,
        "failed_cases": sorted(failed_cases),
    }
