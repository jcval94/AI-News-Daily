"""Adversarial mutations for candidate-selection regressions."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .candidate_models import CandidateCase


def select_rejected_candidate(
    case: CandidateCase,
    selection: dict[str, Any],
) -> tuple[dict[str, Any], set[str]]:
    bad = deepcopy(selection)
    if not case.expected.must_reject_provider_asset_ids:
        raise ValueError(f"{case.id} has no expected rejected candidate to mutate")
    bad_id = case.expected.must_reject_provider_asset_ids[0]
    bad["selected_provider_asset_ids"] = [bad_id]
    bad["unresolved"] = False
    for assessment in bad["assessments"]:
        if assessment["provider_asset_id"] == bad_id:
            assessment["verdict"] = "direct"
            break
    return bad, {
        "selection_expected",
        "required_rejections",
        "selected_identity",
        "selected_rights",
        "period",
        "geography",
        "duplicate_quality",
    }


def drop_required_warning(
    case: CandidateCase,
    selection: dict[str, Any],
) -> tuple[dict[str, Any], set[str]]:
    if not case.expected.required_warnings:
        raise ValueError(f"{case.id} has no required warning")
    bad = deepcopy(selection)
    required = case.expected.required_warnings[0]
    bad["warnings"] = [item for item in bad["warnings"] if item != required]
    return bad, {"required_warnings"}
