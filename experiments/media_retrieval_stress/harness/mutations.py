"""Deterministic adversarial mutations for planner regression tests."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def mutate_fixture(case_id: str, planner: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
    bad = deepcopy(planner)

    if case_id == "franchise_yugioh_time_wizard":
        bad["resolved_entity"]["canonical_name"] = "generic magician"
        bad["resolved_entity"]["identity_anchors"] = ["magician", "clock"]
        bad["queries"][0]["query"] = "generic magician holding a clock"
        return bad, {"canonical_terms", "domain_context", "query_term_groups", "forbidden_terms"}

    if case_id == "product_gemini_google_not_zodiac":
        bad["resolved_entity"]["canonical_name"] = "Gemini constellation"
        bad["resolved_entity"]["identity_anchors"] = ["Gemini", "zodiac"]
        bad["queries"][0]["query"] = "Gemini zodiac constellation"
        return bad, {"domain_context", "query_term_groups", "forbidden_terms"}

    if case_id == "product_claude_anthropic_not_namesakes":
        bad["resolved_entity"]["canonical_name"] = "Claude Monet"
        bad["resolved_entity"]["identity_anchors"] = ["Claude Monet"]
        bad["resolved_entity"]["qualifiers"] = []
        bad["queries"][0]["query"] = "Claude Monet paintings"
        return bad, {"domain_context", "query_term_groups", "forbidden_terms"}

    if case_id == "ambiguity_mercury_fail_closed":
        bad = {
            "schema_version": 1,
            "case_id": case_id,
            "decision": "search",
            "surface_mention": "Mercury",
            "ambiguity_status": "unambiguous",
            "interpretation": "Se asumió que Mercury es el planeta.",
            "resolved_entity": {
                "canonical_name": "Mercury planet",
                "entity_type": "other",
                "identity_anchors": ["Mercury", "planet"],
                "qualifiers": [],
            },
            "queries": [{
                "query": "Mercury planet",
                "language": "en",
                "media_type": "image",
                "purpose": "canonical_identity",
                "anchors": ["Mercury", "planet"],
            }],
            "exclusions": [],
            "risk_flags": ["guessed ambiguous entity"],
            "rights_boundary_acknowledged": True,
        }
        return bad, {"decision", "query_count", "ambiguity_refusal"}

    if case_id == "metaphor_compute_bottleneck_not_bottle":
        bad["resolved_entity"]["canonical_name"] = "glass bottle neck"
        bad["resolved_entity"]["identity_anchors"] = ["bottle"]
        bad["queries"][0]["query"] = "glass bottle neck"
        return bad, {"canonical_terms", "domain_context", "query_term_groups", "forbidden_terms"}

    if case_id == "negation_no_humanoid_robots":
        bad["resolved_entity"]["canonical_name"] = "humanoid robot"
        bad["resolved_entity"]["identity_anchors"] = ["humanoid robot"]
        bad["queries"][0]["query"] = "humanoid robot walking"
        return bad, {"canonical_terms", "domain_context", "query_term_groups", "forbidden_terms"}

    if case_id == "history_lake_nyos_event_not_tourism":
        bad["resolved_entity"]["identity_anchors"] = ["Lake Nyos"]
        bad["resolved_entity"]["qualifiers"] = ["lake"]
        bad["queries"][0]["query"] = "Lake Nyos Cameroon tourism"
        return bad, {"domain_context", "query_term_groups", "forbidden_terms", "period"}

    if case_id == "history_plato_no_fake_photo":
        bad["queries"][0]["query"] = "photograph of Plato alive"
        bad["queries"][0]["anchors"] = ["Plato", "photograph"]
        return bad, {"query_term_groups", "forbidden_terms"}

    raise KeyError(f"No adversarial mutation defined for {case_id}")
