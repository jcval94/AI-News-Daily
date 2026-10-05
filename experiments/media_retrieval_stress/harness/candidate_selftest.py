"""Offline self-test for adversarial candidate selection."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .candidate_evaluate import candidate_selection_signature, evaluate_candidate_selection
from .candidate_models import CandidateCase, CandidateSelectionOutput
from .candidate_mutations import drop_required_warning, select_rejected_candidate
from .contracts import validate as validate_contract
from .gates import evaluate_scorecard
from .profiles import load_profile


HERE = Path(__file__).resolve().parent
LAB_ROOT = HERE.parent
CASES = LAB_ROOT / "cases" / "candidate_selection.json"
FIXTURES = LAB_ROOT / "fixtures" / "candidate_good_selections.json"
PROFILE = LAB_ROOT / "profiles" / "candidate_strict.json"


def synthetic_run(
    cases: list[CandidateCase],
    fixtures: dict[str, dict],
    repetitions: int,
    reasoning_effort: str,
) -> dict[str, Any]:
    case_results = []
    attempts = 0
    for case in cases:
        raw = fixtures[case.id]
        selection = CandidateSelectionOutput.model_validate(raw)
        deterministic = evaluate_candidate_selection(case, selection)
        runs = []
        for repetition in range(1, repetitions + 1):
            attempts += 1
            runs.append({
                "case_id": case.id,
                "repetition": repetition,
                "selection": raw,
                "deterministic": deterministic,
                "passed": True,
                "signature": candidate_selection_signature(selection),
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
        "run_id": "candidate-selftest",
        "started_at": "2026-09-27T00:00:00+00:00",
        "completed_at": "2026-09-27T00:00:01+00:00",
        "config": {
            "schema_version": 1,
            "model": "test-model",
            "repetitions": repetitions,
            "reasoning_effort": reasoning_effort,
            "timeout_seconds": 30,
            "max_output_tokens": 500,
            "critic_enabled": False,
        },
        "source_cases": "cases/candidate_selection.json",
        "source_cases_sha256": "4" * 64,
        "profile_id": "candidate_strict",
        "profile_sha256": "5" * 64,
        "prompt_fingerprint": "6" * 64,
        "summary": {
            "cases": len(cases),
            "repetitions": repetitions,
            "attempts": attempts,
            "selector_passes": attempts,
            "overall_passes": attempts,
        },
        "case_results": case_results,
    }


def run_candidate_selftest() -> dict[str, Any]:
    case_payload = json.loads(CASES.read_text(encoding="utf-8"))
    cases: list[CandidateCase] = []
    for raw in case_payload["cases"]:
        validate_contract("candidate_case.schema.json", raw)
        cases.append(CandidateCase.model_validate(raw))

    fixture_payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    fixtures = {item["case_id"]: item["selection"] for item in fixture_payload["fixtures"]}
    by_id = {case.id: case for case in cases}
    if set(fixtures) != set(by_id):
        raise AssertionError(
            f"candidate fixture/case mismatch: fixtures={sorted(fixtures)} cases={sorted(by_id)}"
        )

    mutation_failures: dict[str, list[str]] = {}
    warning_mutations = 0

    for case_id, case in by_id.items():
        raw = fixtures[case_id]
        validate_contract("candidate_selection.schema.json", raw)
        output = CandidateSelectionOutput.model_validate(raw)
        evaluation = evaluate_candidate_selection(case, output)
        if not evaluation["passed"]:
            raise AssertionError(f"known-good candidate fixture failed for {case_id}: {evaluation}")

        bad_raw, expected_failures = select_rejected_candidate(case, raw)
        validate_contract("candidate_selection.schema.json", bad_raw)
        bad_output = CandidateSelectionOutput.model_validate(bad_raw)
        bad_eval = evaluate_candidate_selection(case, bad_output)
        if bad_eval["passed"]:
            raise AssertionError(f"wrong candidate selection passed for {case_id}: {bad_eval}")
        observed = set(bad_eval["failures"])
        if not expected_failures.intersection(observed):
            raise AssertionError(
                f"candidate mutation for {case_id} failed for wrong reason: "
                f"expected one of {sorted(expected_failures)}, got {sorted(observed)}"
            )
        mutation_failures[case_id] = sorted(observed)

        if case.expected.required_warnings:
            warning_mutations += 1
            warning_raw, expected_warning_failures = drop_required_warning(case, raw)
            validate_contract("candidate_selection.schema.json", warning_raw)
            warning_output = CandidateSelectionOutput.model_validate(warning_raw)
            warning_eval = evaluate_candidate_selection(case, warning_output)
            if warning_eval["passed"]:
                raise AssertionError(f"missing required warning passed for {case_id}")
            if not expected_warning_failures.intersection(set(warning_eval["failures"])):
                raise AssertionError(
                    f"warning mutation for {case_id} did not fail required_warnings: {warning_eval}"
                )

    profile = load_profile(PROFILE)
    run = synthetic_run(cases, fixtures, profile.repetitions, profile.reasoning_effort)
    validate_contract("candidate_run_record.schema.json", run)

    passing_scorecard = evaluate_scorecard(profile, run)
    validate_contract("scorecard.schema.json", passing_scorecard)
    if passing_scorecard["verdict"] != "pass":
        raise AssertionError(f"known-good candidate run failed strict gate: {passing_scorecard}")

    failing_run = deepcopy(run)
    item = failing_run["case_results"][0]
    attempt = item["runs"][0]
    attempt["passed"] = False
    attempt["deterministic"] = deepcopy(attempt["deterministic"])
    attempt["deterministic"]["passed"] = False
    attempt["deterministic"]["checks"]["selection_expected"] = False
    attempt["deterministic"]["failures"] = ["selection_expected"]
    item["pass_rate"] = round(
        sum(bool(row["passed"]) for row in item["runs"]) / len(item["runs"]),
        4,
    )
    failing_run["summary"]["selector_passes"] -= 1
    failing_run["summary"]["overall_passes"] -= 1

    failing_scorecard = evaluate_scorecard(profile, failing_run)
    validate_contract("scorecard.schema.json", failing_scorecard)
    if failing_scorecard["verdict"] != "fail":
        raise AssertionError("candidate strict gate failed to reject selection regression")

    return {
        "candidate_cases": len(cases),
        "candidate_good_fixtures": len(fixtures),
        "candidate_wrong_selections_rejected": len(mutation_failures),
        "candidate_warning_mutations_rejected": warning_mutations,
        "candidate_mutation_failures": mutation_failures,
        "candidate_known_good_scorecard": passing_scorecard["verdict"],
        "candidate_known_bad_scorecard": failing_scorecard["verdict"],
        "candidate_synthetic_attempts": run["summary"]["attempts"],
    }


if __name__ == "__main__":
    print(json.dumps(run_candidate_selftest(), ensure_ascii=False, indent=2))
