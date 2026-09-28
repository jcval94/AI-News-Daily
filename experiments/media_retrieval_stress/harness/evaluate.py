"""Deterministic assertions for semantic retrieval outputs.

These checks deliberately run before the model critic. An eloquent explanation cannot
override a violated case contract.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from .models import PlannerOutput, StressCase


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[^\W_]+", text, flags=re.UNICODE))


def contains(text: str, term: str) -> bool:
    needle = normalize(term)
    haystack = normalize(text)
    return bool(needle) and f" {needle} " in f" {haystack} "


def _identity_blob(output: PlannerOutput) -> str:
    if output.resolved_entity is None:
        return ""
    entity = output.resolved_entity
    return " | ".join([
        entity.canonical_name,
        *entity.identity_anchors,
        *entity.qualifiers,
    ])


def _query_blob(output: PlannerOutput) -> str:
    return " | ".join(query.query for query in output.queries)


def evaluate_planner(case: StressCase, output: PlannerOutput) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    failures: list[str] = []

    checks["case_id"] = output.case_id == case.id
    checks["surface_mention"] = output.surface_mention == case.target.surface_mention
    checks["decision"] = output.decision == case.expected.planner_action
    checks["query_count"] = (
        case.expected.min_queries <= len(output.queries) <= case.expected.max_queries
    )

    if output.decision == "refuse":
        checks["ambiguity_refusal"] = (
            case.target.ambiguity_policy == "refuse_if_ambiguous"
            and output.ambiguity_status in {"ambiguous", "unsupported"}
            and output.resolved_entity is None
            and not output.queries
        )
        checks["identity_type"] = True
        checks["canonical_terms"] = True
        checks["domain_context"] = True
        checks["query_term_groups"] = True
        checks["forbidden_terms"] = True
        checks["period"] = True
        checks["geography"] = True
    else:
        entity = output.resolved_entity
        identity_blob = _identity_blob(output)
        query_blob = _query_blob(output)
        combined = identity_blob + " | " + query_blob + " | " + " | ".join(output.exclusions)

        checks["ambiguity_refusal"] = case.target.ambiguity_policy != "refuse_if_ambiguous"
        checks["identity_type"] = bool(entity and entity.entity_type == case.target.entity_type)
        checks["canonical_terms"] = all(
            contains(identity_blob, term)
            for term in case.target.expected_canonical_terms
        )
        # Domain context may be carried by canonical identity, qualifiers, anchors or queries.
        checks["domain_context"] = all(
            contains(combined, term)
            for term in case.target.domain_context
        )

        def query_satisfies_groups(query: str) -> bool:
            return all(
                any(contains(query, option) for option in group)
                for group in case.retrieval.query_term_groups
            )

        checks["query_term_groups"] = (
            True if not case.retrieval.query_term_groups
            else any(query_satisfies_groups(item.query) for item in output.queries)
        )

        forbidden = [
            *case.target.forbidden_identity_terms,
            *case.retrieval.forbidden_terms,
        ]
        checks["forbidden_terms"] = not any(contains(combined, term) for term in forbidden)

        period_blob = identity_blob + " | " + query_blob
        checks["period"] = (
            True if not case.retrieval.period
            else contains(period_blob, case.retrieval.period)
        )
        checks["geography"] = (
            True if not case.retrieval.geography
            else contains(period_blob, case.retrieval.geography)
        )

    for name, passed in checks.items():
        if not passed:
            failures.append(name)

    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failures": failures,
    }


def canonical_signature(output: PlannerOutput) -> str:
    entity = output.resolved_entity
    canonical = normalize(entity.canonical_name) if entity else ""
    queries = sorted(normalize(item.query) for item in output.queries)
    return "|".join([output.decision, output.ambiguity_status, canonical, *queries])
