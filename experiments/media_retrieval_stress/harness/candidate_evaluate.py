"""Deterministic evaluation for adversarial candidate selection."""
from __future__ import annotations

from typing import Any

from .candidate_models import CandidateCase, CandidateSelectionOutput


def _pixels(width: int | None, height: int | None) -> int:
    return int(width or 0) * int(height or 0)


def evaluate_candidate_selection(
    case: CandidateCase,
    output: CandidateSelectionOutput,
) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    failures: list[str] = []

    candidate_by_id = {item.provider_asset_id: item for item in case.candidates}
    assessment_by_id = {item.provider_asset_id: item for item in output.assessments}
    candidate_ids = set(candidate_by_id)
    assessment_ids = set(assessment_by_id)
    selected = set(output.selected_provider_asset_ids)

    checks["case_id"] = output.case_id == case.id
    checks["assessment_coverage"] = assessment_ids == candidate_ids
    checks["selection_expected"] = selected == set(case.expected.selected_provider_asset_ids)
    checks["required_rejections"] = all(
        item_id not in selected
        and item_id in assessment_by_id
        and assessment_by_id[item_id].verdict == "reject"
        for item_id in case.expected.must_reject_provider_asset_ids
    )
    checks["unresolved"] = output.unresolved == case.expected.unresolved
    checks["required_warnings"] = set(case.expected.required_warnings).issubset(set(output.warnings))

    selected_assessments = [
        assessment_by_id[item_id]
        for item_id in selected
        if item_id in assessment_by_id
    ]
    checks["selected_identity"] = all(item.identity_match for item in selected_assessments)
    checks["selected_rights"] = all(
        candidate_by_id[item.provider_asset_id].rights_status == "eligible"
        and item.rights_eligible
        for item in selected_assessments
    )
    checks["selected_verdict"] = all(
        item.verdict == "direct"
        or (case.policy.allow_contextual_fallback and item.verdict == "contextual")
        for item in selected_assessments
    )

    if case.policy.period:
        checks["period"] = all(
            item.period_match == "match"
            for item in selected_assessments
        )
    else:
        checks["period"] = True

    if case.policy.geography:
        checks["geography"] = all(
            item.geography_match == "match"
            for item in selected_assessments
        )
    else:
        checks["geography"] = True

    checks["fail_closed"] = not (
        case.policy.exactness == "exact"
        and output.unresolved
        and bool(selected)
    )

    duplicate_ok = True
    if case.policy.prefer_highest_quality_same_identity:
        groups: dict[str, list] = {}
        for candidate in case.candidates:
            content_hash = str(candidate.metadata.get("content_hash") or "")
            if content_hash:
                groups.setdefault(content_hash, []).append(candidate)
        for group in groups.values():
            if len(group) < 2:
                continue
            best = max(group, key=lambda item: _pixels(item.width, item.height))
            selected_in_group = [item for item in group if item.provider_asset_id in selected]
            if selected_in_group and best.provider_asset_id not in selected:
                duplicate_ok = False
    checks["duplicate_quality"] = duplicate_ok

    for name, passed in checks.items():
        if not passed:
            failures.append(name)

    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failures": failures,
    }


def candidate_selection_signature(output: CandidateSelectionOutput) -> str:
    selected = ",".join(sorted(output.selected_provider_asset_ids))
    verdicts = ",".join(
        f"{item.provider_asset_id}:{item.verdict}"
        for item in sorted(output.assessments, key=lambda value: value.provider_asset_id)
    )
    return f"unresolved={int(output.unresolved)}|selected={selected}|{verdicts}"
