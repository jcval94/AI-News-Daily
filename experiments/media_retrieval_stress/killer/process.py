"""Deterministic four-stage state machine for killer retrieval experiments."""
from __future__ import annotations

from typing import Any


def classify(case: dict[str, Any]) -> str:
    entity = case["entity_resolution"]["status"]
    discovery = case["exact_discovery"]["status"]
    visual = case["visual_verification"]["status"]
    usability = case["usability"]["status"]

    if entity == "ambiguous":
        return "AMBIGUOUS"
    if entity != "pass":
        return "NOT_FOUND"
    if discovery == "not_found":
        return "NOT_FOUND"
    if discovery == "found_contextual":
        return "FOUND_CONTEXTUAL"
    if visual == "not_verified":
        return "NOT_FOUND"
    if usability == "usable":
        return "FOUND_EXACT_USABLE"
    if usability in {"reference_only", "blocked", "review_required"}:
        return "FOUND_EXACT_REFERENCE_ONLY"
    raise ValueError(f"unsupported killer state combination: {entity}/{discovery}/{visual}/{usability}")


def validate_transitions(case: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    expected = classify(case)
    if case["final_status"] != expected:
        problems.append(
            f"final_status={case['final_status']} but state machine derives {expected}"
        )

    if (
        case["exact_discovery"]["status"] == "found_exact"
        and case["final_status"] == "FOUND_CONTEXTUAL"
    ):
        problems.append("exact discovery was silently degraded to contextual media")

    if (
        case["usability"]["status"] != "usable"
        and case["final_status"] == "FOUND_EXACT_USABLE"
    ):
        problems.append("non-usable media was promoted to automatic acquisition")

    if (
        case["usability"]["status"] == "reference_only"
        and not case["exact_discovery"]["best_reference"]
    ):
        problems.append("reference_only requires an exact retained reference")

    return problems
