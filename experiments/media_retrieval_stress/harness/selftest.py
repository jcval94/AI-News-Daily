"""Offline self-test for contracts, cases and deterministic assertions."""
from __future__ import annotations

import json
from pathlib import Path

from .contracts import contract_names, validate as validate_contract
from .evaluate import evaluate_planner
from .models import CriticOutput, PlannerOutput, RunConfig, StressCase


HERE = Path(__file__).resolve().parent
LAB_ROOT = HERE.parent
CASES = LAB_ROOT / "cases" / "core.json"


def main() -> None:
    names = contract_names()
    expected_contracts = {
        "case.schema.json",
        "planner_output.schema.json",
        "critic_output.schema.json",
        "run_config.schema.json",
        "run_record.schema.json",
        "candidate.schema.json",
    }
    if set(names) != expected_contracts:
        raise AssertionError(f"unexpected contract set: {names}")

    case_payload = json.loads(CASES.read_text(encoding="utf-8"))
    cases = []
    for raw in case_payload["cases"]:
        validate_contract("case.schema.json", raw)
        cases.append(StressCase.model_validate(raw))

    by_id = {case.id: case for case in cases}
    if "franchise_yugioh_time_wizard" not in by_id:
        raise AssertionError("canonical Yu-Gi-Oh stress case is missing")

    good_raw = {
        "schema_version": 1,
        "case_id": "franchise_yugioh_time_wizard",
        "decision": "search",
        "surface_mention": "El Mago del Tiempo",
        "ambiguity_status": "unambiguous",
        "interpretation": "La mención se refiere a Time Wizard, carta de Yu-Gi-Oh! asociada a Joey Wheeler.",
        "resolved_entity": {
            "canonical_name": "Time Wizard",
            "entity_type": "franchise_object",
            "identity_anchors": ["Yu-Gi-Oh!", "Time Wizard"],
            "qualifiers": ["Joey Wheeler"],
        },
        "queries": [{
            "query": "Yu-Gi-Oh Time Wizard trading card Joey Wheeler",
            "language": "en",
            "media_type": "image",
            "purpose": "canonical_identity",
            "anchors": ["Yu-Gi-Oh", "Time Wizard", "Joey Wheeler"],
        }],
        "exclusions": ["generic magician", "weather wizard"],
        "risk_flags": ["commercial copyrighted trading card"],
        "rights_boundary_acknowledged": True,
    }
    validate_contract("planner_output.schema.json", good_raw)
    good = PlannerOutput.model_validate(good_raw)
    good_eval = evaluate_planner(by_id["franchise_yugioh_time_wizard"], good)
    if not good_eval["passed"]:
        raise AssertionError(f"known-good Time Wizard fixture failed: {good_eval}")

    bad = good.model_copy(deep=True)
    bad.queries[0].query = "generic magician holding a clock"
    bad_eval = evaluate_planner(by_id["franchise_yugioh_time_wizard"], bad)
    if bad_eval["passed"]:
        raise AssertionError(f"known-bad generic magician fixture was not rejected: {bad_eval}")
    if not {"query_term_groups", "forbidden_terms"}.intersection(bad_eval["failures"]):
        raise AssertionError(f"wrong failure taxonomy for generic magician fixture: {bad_eval}")

    mercury = by_id["ambiguity_mercury_fail_closed"]
    refusal_raw = {
        "schema_version": 1,
        "case_id": mercury.id,
        "decision": "refuse",
        "surface_mention": "Mercury",
        "ambiguity_status": "ambiguous",
        "interpretation": "El contexto no distingue planeta, elemento, marca, persona u otra entidad.",
        "resolved_entity": None,
        "queries": [],
        "exclusions": [],
        "risk_flags": ["genuine unresolved polysemy"],
        "rights_boundary_acknowledged": True,
    }
    validate_contract("planner_output.schema.json", refusal_raw)
    refusal = PlannerOutput.model_validate(refusal_raw)
    refusal_eval = evaluate_planner(mercury, refusal)
    if not refusal_eval["passed"]:
        raise AssertionError(f"known-good ambiguity refusal failed: {refusal_eval}")

    critic_raw = {
        "schema_version": 1,
        "case_id": good.case_id,
        "verdict": "pass",
        "checks": {
            "identity_preserved": True,
            "qualifiers_preserved": True,
            "ambiguity_handled": True,
            "no_forbidden_drift": True,
            "negation_respected": True,
            "exactness_preserved": True,
            "queries_searchable": True,
        },
        "failure_codes": [],
        "summary": "La identidad y los qualifiers se preservan sin drift semántico.",
    }
    validate_contract("critic_output.schema.json", critic_raw)
    CriticOutput.model_validate(critic_raw)

    config = RunConfig(
        model="test-model",
        repetitions=1,
        reasoning_effort="none",
        timeout_seconds=30,
        max_output_tokens=500,
        critic_enabled=True,
    )
    validate_contract("run_config.schema.json", config.model_dump())

    run_record = {
        "schema_version": 1,
        "run_id": "selftest",
        "started_at": "2026-09-27T00:00:00+00:00",
        "completed_at": "2026-09-27T00:00:01+00:00",
        "config": config.model_dump(),
        "source_cases": "cases/core.json",
        "summary": {
            "cases": 1,
            "repetitions": 1,
            "attempts": 1,
            "planner_passes": 1,
            "critic_passes": 1,
            "overall_passes": 1,
        },
        "case_results": [{
            "case_id": good.case_id,
            "runs": [],
            "pass_rate": 1.0,
            "stable": True,
            "errors": 0,
        }],
    }
    validate_contract("run_record.schema.json", run_record)

    print(
        json.dumps(
            {
                "contracts": len(names),
                "cases": len(cases),
                "time_wizard_fixture": "pass",
                "wrong_generic_fixture": "rejected",
                "ambiguity_fixture": "pass",
                "critic_contract": "pass",
                "run_record_contract": "pass",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
