"""Run adversarial candidate-selection stress experiments.

All inputs and outputs stay inside experiments/media_retrieval_stress/.
No production media acquisition code or provider API is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from .candidate_evaluate import candidate_selection_signature, evaluate_candidate_selection
from .candidate_models import CandidateCase, CandidateSelectionOutput
from .candidate_prompts import CANDIDATE_SELECTOR_SYSTEM, selector_input
from .contracts import validate as validate_contract
from .gates import evaluate_scorecard
from .llm import LLMCallError, call_structured
from .models import ExperimentProfile, RunConfig
from .profiles import load_profile


HERE = Path(__file__).resolve().parent
LAB_ROOT = HERE.parent
DEFAULT_CASES = LAB_ROOT / "cases" / "candidate_selection.json"
DEFAULT_PROFILE = LAB_ROOT / "profiles" / "candidate_strict.json"
RESULTS_ROOT = LAB_ROOT / "results"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_cases(path: Path) -> list[CandidateCase]:
    resolved = path.resolve()
    if not resolved.is_relative_to((LAB_ROOT / "cases").resolve()):
        raise ValueError("candidate stress cases must live inside the isolated cases directory")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("cases"), list):
        raise ValueError("candidate case file must contain schema_version=1 and a cases array")
    cases = []
    for item in payload["cases"]:
        validate_contract("candidate_case.schema.json", item)
        cases.append(CandidateCase.model_validate(item))
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("candidate case ids must be unique")
    return cases


def select_cases(cases: list[CandidateCase], profile: ExperimentProfile) -> list[CandidateCase]:
    if not profile.case_ids:
        return cases
    by_id = {case.id: case for case in cases}
    missing = sorted(set(profile.case_ids) - set(by_id))
    if missing:
        raise ValueError(f"profile references unknown candidate case ids: {missing}")
    wanted = set(profile.case_ids)
    return [case for case in cases if case.id in wanted]


def write_json(path: Path, payload: Any) -> None:
    resolved = path.resolve()
    if not resolved.is_relative_to(RESULTS_ROOT.resolve()):
        raise ValueError("candidate harness attempted to write outside isolated results")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    resolved = path.resolve()
    if not resolved.is_relative_to(RESULTS_ROOT.resolve()):
        raise ValueError("candidate harness attempted to write outside isolated results")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(text, encoding="utf-8")


def run_one(case: CandidateCase, config: RunConfig, repetition: int) -> dict[str, Any]:
    record: dict[str, Any] = {
        "case_id": case.id,
        "repetition": repetition,
        "started_at": utc_now(),
        "selection": None,
        "selector_metadata": None,
        "deterministic": None,
        "passed": False,
        "error": None,
    }
    try:
        raw, meta = call_structured(
            system_prompt=CANDIDATE_SELECTOR_SYSTEM,
            user_prompt=selector_input(case),
            schema_file="candidate_selection.schema.json",
            schema_name="media_stress_candidate_selection",
            config=config,
        )
        validate_contract("candidate_selection.schema.json", raw)
        selection = CandidateSelectionOutput.model_validate(raw)
        deterministic = evaluate_candidate_selection(case, selection)
        record["selection"] = selection.model_dump()
        record["selector_metadata"] = meta
        record["deterministic"] = deterministic
        record["passed"] = bool(deterministic["passed"])
        record["signature"] = candidate_selection_signature(selection)
    except (LLMCallError, JsonSchemaValidationError, ValueError, TypeError) as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    record["completed_at"] = utc_now()
    return record


def build_payload(
    *,
    run_id: str,
    started_at: str,
    completed_at: str,
    config: RunConfig,
    profile: ExperimentProfile,
    source_profile: Path,
    source_cases: Path,
    cases: list[CandidateCase],
    all_runs: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    case_results = []
    selector_passes = overall_passes = attempts = 0
    for case in cases:
        runs = all_runs[case.id]
        attempts += len(runs)
        selector_passes += sum(bool((row.get("deterministic") or {}).get("passed")) for row in runs)
        overall_passes += sum(bool(row.get("passed")) for row in runs)
        signatures = {
            str(row.get("signature"))
            for row in runs
            if row.get("selection") and row.get("signature")
        }
        case_results.append({
            "case_id": case.id,
            "runs": runs,
            "pass_rate": round(sum(bool(row.get("passed")) for row in runs) / max(1, len(runs)), 4),
            "stable": len(signatures) == 1 and bool(signatures),
            "errors": sum(bool(row.get("error")) for row in runs),
        })

    return {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "config": config.model_dump(),
        "source_cases": str(source_cases.resolve().relative_to(LAB_ROOT.resolve())),
        "source_cases_sha256": hashlib.sha256(source_cases.read_bytes()).hexdigest(),
        "profile_id": profile.id,
        "profile_sha256": hashlib.sha256(source_profile.read_bytes()).hexdigest(),
        "prompt_fingerprint": hashlib.sha256(CANDIDATE_SELECTOR_SYSTEM.encode("utf-8")).hexdigest(),
        "summary": {
            "cases": len(cases),
            "repetitions": config.repetitions,
            "attempts": attempts,
            "selector_passes": selector_passes,
            "overall_passes": overall_passes,
        },
        "case_results": case_results,
    }


def summary_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Candidate selection stress run",
        "",
        f"- run: `{payload['run_id']}`",
        f"- profile: `{payload['profile_id']}`",
        f"- model: `{payload['config']['model']}`",
        f"- passes: **{summary['overall_passes']}/{summary['attempts']}**",
        "",
        "| Case | Pass rate | Stable selection | Errors |",
        "|---|---:|---:|---:|",
    ]
    for item in payload["case_results"]:
        lines.append(
            f"| {item['case_id']} | {item['pass_rate']:.0%} | "
            f"{'yes' if item['stable'] else 'no'} | {item['errors']} |"
        )
    return "\n".join(lines) + "\n"


def scorecard_markdown(scorecard: dict[str, Any]) -> str:
    metrics = scorecard["metrics"]
    lines = [
        "# Candidate selection scorecard",
        "",
        f"- verdict: **{scorecard['verdict'].upper()}**",
        f"- overall pass rate: **{metrics['overall_pass_rate']:.1%}**",
        f"- minimum case pass rate: **{metrics['minimum_case_pass_rate']:.1%}**",
        f"- stable selections: **{metrics['stable_cases']}/{metrics['total_cases']}**",
        f"- errors: **{metrics['errors']}**",
        f"- hard failures: **{metrics['hard_fail_count']}**",
    ]
    for failure in scorecard["hard_failures"]:
        lines.append(
            f"- `{failure['case_id']}` r{failure['repetition']}: "
            f"`{failure['code']}` — {failure['detail']}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", ""))
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--max-output-tokens", type=int, default=3500)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    if not args.model.strip():
        raise SystemExit("Provide --model or OPENAI_MODEL")

    profile_path = args.profile.resolve()
    profile = load_profile(profile_path)
    if profile.critic_enabled:
        raise SystemExit("candidate-selection profiles must set critic_enabled=false")

    config = RunConfig(
        model=args.model.strip(),
        repetitions=profile.repetitions,
        reasoning_effort=profile.reasoning_effort,
        timeout_seconds=args.timeout_seconds,
        max_output_tokens=args.max_output_tokens,
        critic_enabled=False,
    )
    validate_contract("run_config.schema.json", config.model_dump())

    cases = select_cases(read_cases(args.cases), profile)
    if not cases:
        raise SystemExit("profile selected zero candidate cases")

    started = utc_now()
    run_id = args.run_id.strip() or (
        "candidate-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", run_id):
        raise SystemExit("run-id may contain only letters, numbers, underscore and hyphen")
    run_dir = (RESULTS_ROOT / run_id).resolve()
    if not run_dir.is_relative_to(RESULTS_ROOT.resolve()):
        raise SystemExit("candidate output escaped isolated results directory")

    all_runs: dict[str, list[dict[str, Any]]] = {case.id: [] for case in cases}
    for case in cases:
        for repetition in range(1, config.repetitions + 1):
            record = run_one(case, config, repetition)
            all_runs[case.id].append(record)
            write_json(run_dir / "candidate_cases" / case.id / f"r{repetition:02d}.json", record)
            partial = build_payload(
                run_id=run_id,
                started_at=started,
                completed_at=utc_now(),
                config=config,
                profile=profile,
                source_profile=profile_path,
                source_cases=args.cases,
                cases=cases,
                all_runs=all_runs,
            )
            validate_contract("candidate_run_record.schema.json", partial)
            write_json(run_dir / "candidate_run.json", partial)
            write_text(run_dir / "CANDIDATE_SUMMARY.md", summary_markdown(partial))
            print(
                f"{case.id} r{repetition}: "
                + ("PASS" if record["passed"] else "FAIL")
                + (f" — {record['error']}" if record.get("error") else ""),
                flush=True,
            )

    final = build_payload(
        run_id=run_id,
        started_at=started,
        completed_at=utc_now(),
        config=config,
        profile=profile,
        source_profile=profile_path,
        source_cases=args.cases,
        cases=cases,
        all_runs=all_runs,
    )
    validate_contract("candidate_run_record.schema.json", final)
    write_json(run_dir / "candidate_run.json", final)
    write_text(run_dir / "CANDIDATE_SUMMARY.md", summary_markdown(final))

    scorecard = evaluate_scorecard(profile, final)
    validate_contract("scorecard.schema.json", scorecard)
    write_json(run_dir / "CANDIDATE_SCORECARD.json", scorecard)
    write_text(run_dir / "CANDIDATE_SCORECARD.md", scorecard_markdown(scorecard))

    print(json.dumps({"summary": final["summary"], "scorecard": scorecard}, ensure_ascii=False, indent=2))
    if args.enforce and scorecard["verdict"] != "pass":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
