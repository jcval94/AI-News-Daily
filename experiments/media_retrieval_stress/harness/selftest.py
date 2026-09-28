"""Offline self-test for contracts, cases and deterministic assertions."""
from __future__ import annotations

import json
from pathlib import Path

from .contracts import contract_names, validate as validate_contract
from .evaluate import evaluate_planner
from .models import CriticOutput, PlannerOutput, RunConfig, StressCase
from .mutations import mutate_fixture


HERE = Path(__file__).resolve().parent
LAB_ROOT = HERE.parent
CASES = LAB_ROOT / "cases" / "core.json"
FIXTURES = LAB_ROOT / "fixtures" / "core_good_plans.json"


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
    cases: list[StressCase] = []
    for raw in case_payload["cases"]:
        validate_contract("case.schema.json", raw)
        cases.append(StressCase.model_validate(raw))

    by_id = {case.id: case for case in cases}
    fixture_payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    fixtures = {item["case_id"]: item["planner"] for item in fixture_payload["fixtures"]}

    if set(fixtures) != set(by_id):
        raise AssertionError(
            f"fixture/case mismatch: fixtures={sorted(fixtures)} cases={sorted(by_id)}"
        )

    good_results = {}
    mutation_results = {}
    for case_id, case in by_id.items():
        good_raw = fixtures[case_id]
        validate_contract("planner_output.schema.json", good_raw)
        good = PlannerOutput.model_validate(good_raw)
        good_eval = evaluate_planner(case, good)
        if not good_eval["passed"]:
            raise AssertionError(f"known-good fixture failed for {case_id}: {good_eval}")
        good_results[case_id] = good_eval

        bad_raw, expected_failures = mutate_fixture(case_id, good_raw)
        validate_contract("planner_output.schema.json", bad_raw)
        bad = PlannerOutput.model_validate(bad_raw)
        bad_eval = evaluate_planner(case, bad)
        if bad_eval["passed"]:
            raise AssertionError(f"known-bad mutation passed for {case_id}: {bad_eval}")
        observed = set(bad_eval["failures"])
        if not expected_failures.intersection(observed):
            raise AssertionError(
                f"mutation for {case_id} failed for the wrong reason: "
                f"expected one of {sorted(expected_failures)}, got {sorted(observed)}"
            )
        mutation_results[case_id] = sorted(observed)

    critic_raw = {
        "schema_version": 1,
        "case_id": "franchise_yugioh_time_wizard",
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
        "source_cases_sha256": "0" * 64,
        "prompt_fingerprints": {
            "planner_sha256": "1" * 64,
            "critic_sha256": "2" * 64,
        },
        "summary": {
            "cases": len(cases),
            "repetitions": 1,
            "attempts": len(cases),
            "planner_passes": len(cases),
            "critic_passes": len(cases),
            "overall_passes": len(cases),
        },
        "case_results": [
            {
                "case_id": case.id,
                "runs": [],
                "pass_rate": 1.0,
                "stable": True,
                "errors": 0,
            }
            for case in cases
        ],
    }
    validate_contract("run_record.schema.json", run_record)

    print(
        json.dumps(
            {
                "contracts": len(names),
                "cases": len(cases),
                "good_fixtures": len(good_results),
                "adversarial_mutations_rejected": len(mutation_results),
                "mutation_failures": mutation_results,
                "critic_contract": "pass",
                "run_record_contract": "pass",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
