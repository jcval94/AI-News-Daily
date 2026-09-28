"""Offline self-test for contracts, fixtures, mutations and aggregate gates."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from .candidate_selftest import run_candidate_selftest
from .contracts import contract_names, validate as validate_contract
from .evaluate import canonical_signature, evaluate_planner
from .gates import evaluate_scorecard
from .models import CriticOutput, PlannerOutput, RunConfig, StressCase
from .mutations import mutate_fixture
from .profiles import load_profile


HERE = Path(__file__).resolve().parent
LAB_ROOT = HERE.parent
CASES = LAB_ROOT / "cases" / "core.json"
FIXTURES = LAB_ROOT / "fixtures" / "core_good_plans.json"
STRICT_PROFILE = LAB_ROOT / "profiles" / "core_strict.json"
REPEAT_PROFILE = LAB_ROOT / "profiles" / "core_repeatability.json"


def passing_critic(case_id: str) -> dict:
    return {
        "schema_version": 1,
        "case_id": case_id,
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
        "summary": "La identidad, los qualifiers y la intención de búsqueda se preservan.",
    }


def build_synthetic_run(cases: list[StressCase], fixtures: dict[str, dict], profile) -> dict:
    repetitions = profile.repetitions
    case_results = []
    attempts = 0
    for case in cases:
        planner_raw = fixtures[case.id]
        planner = PlannerOutput.model_validate(planner_raw)
        deterministic = evaluate_planner(case, planner)
        runs = []
        for repetition in range(1, repetitions + 1):
            attempts += 1
            runs.append({
                "case_id": case.id,
                "repetition": repetition,
                "planner": planner_raw,
                "deterministic": deterministic,
                "critic": passing_critic(case.id),
                "passed": True,
                "signature": canonical_signature(planner),
                "error": None,
            })
        case_results.append({
            "case_id": case.id,
            "runs": runs,
            "pass_rate": 1.0,
            "stable": True,
            "errors": 0,
        })
    return {
        "schema_version": 1,
        "run_id": "selftest",
        "started_at": "2026-09-27T00:00:00+00:00",
        "completed_at": "2026-09-27T00:00:01+00:00",
        "config": {
            "schema_version": 1,
            "model": "test-model",
            "repetitions": repetitions,
            "reasoning_effort": profile.reasoning_effort,
            "timeout_seconds": 30,
            "max_output_tokens": 500,
            "critic_enabled": profile.critic_enabled,
        },
        "source_cases": "cases/core.json",
        "source_cases_sha256": "0" * 64,
        "profile_id": "core_strict",
        "profile_sha256": "3" * 64,
        "prompt_fingerprints": {
            "planner_sha256": "1" * 64,
            "critic_sha256": "2" * 64,
        },
        "summary": {
            "cases": len(cases),
            "repetitions": repetitions,
            "attempts": attempts,
            "planner_passes": attempts,
            "critic_passes": attempts,
            "overall_passes": attempts,
        },
        "case_results": case_results,
    }


def main() -> None:
    names = contract_names()
    expected_contracts = {
        "candidate.schema.json",
        "candidate_case.schema.json",
        "candidate_selection.schema.json",
        "case.schema.json",
        "critic_output.schema.json",
        "experiment_profile.schema.json",
        "planner_output.schema.json",
        "run_config.schema.json",
        "run_record.schema.json",
        "scorecard.schema.json",
    }
    if set(names) != expected_contracts:
        raise AssertionError(f"unexpected contract set: {names}")

    case_payload = json.loads(CASES.read_text(encoding="utf-8"))
    cases: list[StressCase] = []
    for raw in case_payload["cases"]:
        validate_contract("case.schema.json", raw)
        cases.append(StressCase.model_validate(raw))

    fixture_payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    fixtures = {item["case_id"]: item["planner"] for item in fixture_payload["fixtures"]}
    by_id = {case.id: case for case in cases}
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

    critic_raw = passing_critic("franchise_yugioh_time_wizard")
    validate_contract("critic_output.schema.json", critic_raw)
    CriticOutput.model_validate(critic_raw)

    config = RunConfig(
        model="test-model",
        repetitions=3,
        reasoning_effort="none",
        timeout_seconds=30,
        max_output_tokens=500,
        critic_enabled=True,
    )
    validate_contract("run_config.schema.json", config.model_dump())

    strict_profile = load_profile(STRICT_PROFILE)
    repeat_profile = load_profile(REPEAT_PROFILE)
    if strict_profile.id != "core_strict" or repeat_profile.id != "core_repeatability":
        raise AssertionError("profile ids do not match expected values")

    run_record = build_synthetic_run(cases, fixtures, strict_profile)
    validate_contract("run_record.schema.json", run_record)

    passing_scorecard = evaluate_scorecard(strict_profile, run_record)
    validate_contract("scorecard.schema.json", passing_scorecard)
    if passing_scorecard["verdict"] != "pass":
        raise AssertionError(f"known-good run did not pass strict gate: {passing_scorecard}")

    failing_run = deepcopy(run_record)
    first_case = failing_run["case_results"][0]
    first_attempt = first_case["runs"][0]
    first_attempt["passed"] = False
    first_attempt["deterministic"] = deepcopy(first_attempt["deterministic"])
    first_attempt["deterministic"]["passed"] = False
    first_attempt["deterministic"]["checks"]["forbidden_terms"] = False
    first_attempt["deterministic"]["failures"] = ["forbidden_terms"]
    first_case["pass_rate"] = round(
        sum(bool(row["passed"]) for row in first_case["runs"]) / len(first_case["runs"]),
        4,
    )
    failing_run["summary"]["overall_passes"] -= 1

    failing_scorecard = evaluate_scorecard(strict_profile, failing_run)
    validate_contract("scorecard.schema.json", failing_scorecard)
    if failing_scorecard["verdict"] != "fail":
        raise AssertionError("strict gate failed to reject a forbidden-term regression")
    if not any(item["code"] == "forbidden_terms" for item in failing_scorecard["hard_failures"]):
        raise AssertionError("strict gate did not preserve the forbidden-term failure reason")

    candidate_summary = run_candidate_selftest()

    print(
        json.dumps(
            {
                "contracts": len(names),
                "cases": len(cases),
                "good_fixtures": len(good_results),
                "adversarial_mutations_rejected": len(mutation_results),
                "mutation_failures": mutation_results,
                "profiles": [strict_profile.id, repeat_profile.id],
                "known_good_scorecard": passing_scorecard["verdict"],
                "known_bad_scorecard": failing_scorecard["verdict"],
                "critic_contract": "pass",
                "run_record_contract": "pass",
                **candidate_summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
