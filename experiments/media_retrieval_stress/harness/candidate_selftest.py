"""Offline self-test for adversarial candidate selection."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .candidate_evaluate import evaluate_candidate_selection
from .candidate_models import CandidateCase, CandidateSelectionOutput
from .candidate_mutations import drop_required_warning, select_rejected_candidate
from .contracts import validate as validate_contract


HERE = Path(__file__).resolve().parent
LAB_ROOT = HERE.parent
CASES = LAB_ROOT / "cases" / "candidate_selection.json"
FIXTURES = LAB_ROOT / "fixtures" / "candidate_good_selections.json"


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

    return {
        "candidate_cases": len(cases),
        "candidate_good_fixtures": len(fixtures),
        "candidate_wrong_selections_rejected": len(mutation_failures),
        "candidate_warning_mutations_rejected": warning_mutations,
        "candidate_mutation_failures": mutation_failures,
    }


if __name__ == "__main__":
    print(json.dumps(run_candidate_selftest(), ensure_ascii=False, indent=2))
