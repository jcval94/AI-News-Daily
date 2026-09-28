"""Offline self-test for contracts, cases and deterministic assertions."""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from .evaluate import evaluate_planner
from .models import PlannerOutput, StressCase


HERE = Path(__file__).resolve().parent
LAB_ROOT = HERE.parent
CONTRACTS = LAB_ROOT / "contracts"
CASES = LAB_ROOT / "cases" / "core.json"


def load(name: str):
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def main() -> None:
    schema_names = [
        "case.schema.json",
        "planner_output.schema.json",
        "critic_output.schema.json",
        "run_config.schema.json",
        "run_record.schema.json",
        "candidate.schema.json",
    ]
    for name in schema_names:
        Draft202012Validator.check_schema(load(name))

    case_payload = json.loads(CASES.read_text(encoding="utf-8"))
    case_schema = Draft202012Validator(load("case.schema.json"))
    cases = []
    for raw in case_payload["cases"]:
        case_schema.validate(raw)
        cases.append(StressCase.model_validate(raw))

    by_id = {case.id: case for case in cases}
    if "franchise_yugioh_time_wizard" not in by_id:
        raise AssertionError("canonical Yu-Gi-Oh stress case is missing")

    good = PlannerOutput.model_validate({
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
    })
    good_eval = evaluate_planner(by_id["franchise_yugioh_time_wizard"], good)
    if not good_eval["passed"]:
        raise AssertionError(f"known-good Time Wizard fixture failed: {good_eval}")

    bad = good.model_copy(deep=True)
    bad.queries[0].query = "generic magician holding a clock"
    bad_eval = evaluate_planner(by_id["franchise_yugioh_time_wizard"], bad)
    if bad_eval["passed"] or "query_term_groups" not in bad_eval["failures"]:
        raise AssertionError(f"known-bad generic magician fixture was not rejected: {bad_eval}")

    mercury = by_id["ambiguity_mercury_fail_closed"]
    refusal = PlannerOutput.model_validate({
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
    })
    refusal_eval = evaluate_planner(mercury, refusal)
    if not refusal_eval["passed"]:
        raise AssertionError(f"known-good ambiguity refusal failed: {refusal_eval}")

    print(
        json.dumps(
            {
                "schemas": len(schema_names),
                "cases": len(cases),
                "time_wizard_fixture": "pass",
                "wrong_generic_fixture": "rejected",
                "ambiguity_fixture": "pass",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
