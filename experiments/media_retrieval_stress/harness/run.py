"""Run adversarial semantic multimedia retrieval stress experiments.

This module writes only inside experiments/media_retrieval_stress/results/.
It does not call production media acquisition code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import validate as validate_contract
from .evaluate import canonical_signature, evaluate_planner
from .llm import LLMCallError, call_structured
from .models import CriticOutput, PlannerOutput, RunConfig, StressCase
from .prompts import CRITIC_SYSTEM, PLANNER_SYSTEM, critic_input, planner_input


HERE = Path(__file__).resolve().parent
LAB_ROOT = HERE.parent
DEFAULT_CASES = LAB_ROOT / "cases" / "core.json"
RESULTS_ROOT = LAB_ROOT / "results"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_cases(path: Path) -> list[StressCase]:
    resolved = path.resolve()
    cases_root = (LAB_ROOT / "cases").resolve()
    if not resolved.is_relative_to(cases_root):
        raise ValueError("stress cases must live inside experiments/media_retrieval_stress/cases")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("cases"), list):
        raise ValueError("case file must contain schema_version=1 and a cases array")
    cases = []
    for item in payload["cases"]:
        validate_contract("case.schema.json", item)
        cases.append(StressCase.model_validate(item))
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("case ids must be unique")
    return cases


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_one(case: StressCase, config: RunConfig, repetition: int) -> dict[str, Any]:
    record: dict[str, Any] = {
        "case_id": case.id,
        "repetition": repetition,
        "started_at": utc_now(),
        "planner": None,
        "planner_metadata": None,
        "deterministic": None,
        "critic": None,
        "critic_metadata": None,
        "passed": False,
        "error": None,
    }
    try:
        planner_raw, planner_meta = call_structured(
            system_prompt=PLANNER_SYSTEM,
            user_prompt=planner_input(case),
            schema_file="planner_output.schema.json",
            schema_name="media_stress_planner_output",
            config=config,
        )
        validate_contract("planner_output.schema.json", planner_raw)
        planner = PlannerOutput.model_validate(planner_raw)
        deterministic = evaluate_planner(case, planner)
        record["planner"] = planner.model_dump()
        record["planner_metadata"] = planner_meta
        record["deterministic"] = deterministic

        critic_pass = True
        if config.critic_enabled:
            critic_raw, critic_meta = call_structured(
                system_prompt=CRITIC_SYSTEM,
                user_prompt=critic_input(case, planner),
                schema_file="critic_output.schema.json",
                schema_name="media_stress_critic_output",
                config=config,
            )
            validate_contract("critic_output.schema.json", critic_raw)
            critic = CriticOutput.model_validate(critic_raw)
            if critic.case_id != case.id:
                raise ValueError("critic case_id does not match input case")
            record["critic"] = critic.model_dump()
            record["critic_metadata"] = critic_meta
            critic_pass = critic.verdict == "pass"

        record["passed"] = bool(deterministic["passed"] and critic_pass)
        record["signature"] = canonical_signature(planner)
    except (LLMCallError, ValueError, TypeError) as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    record["completed_at"] = utc_now()
    return record


def markdown_summary(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Multimedia retrieval semantic stress run",
        "",
        f"- run: `{payload['run_id']}`",
        f"- model: `{payload['config']['model']}`",
        f"- cases: **{summary['cases']}**",
        f"- repetitions: **{summary['repetitions']}**",
        f"- overall passes: **{summary['overall_passes']}/{summary['attempts']}**",
        "",
        "| Case | Pass rate | Stable identity | Errors |",
        "|---|---:|---:|---:|",
    ]
    for item in payload["case_results"]:
        lines.append(
            f"| {item['case_id']} | {item['pass_rate']:.0%} | "
            f"{'yes' if item['stable'] else 'no'} | {item['errors']} |"
        )
    lines.extend([
        "",
        "A stable identity means all successful planner calls normalized to the same decision, ambiguity status and canonical entity.",
        "Query wording may vary without making identity stability fail.",
    ])
    return "\n".join(lines) + "\n"


def build_payload(
    *,
    run_id: str,
    started_at: str,
    completed_at: str,
    config: RunConfig,
    source_cases: Path,
    cases: list[StressCase],
    all_runs: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    case_results = []
    planner_passes = critic_passes = overall_passes = attempts = 0
    for case in cases:
        runs = all_runs[case.id]
        attempts += len(runs)
        planner_passes += sum(bool((row.get("deterministic") or {}).get("passed")) for row in runs)
        critic_passes += sum(
            bool(row.get("critic") and row["critic"].get("verdict") == "pass")
            if config.critic_enabled else True
            for row in runs
        )
        overall_passes += sum(bool(row.get("passed")) for row in runs)
        signatures = {
            str(row.get("signature"))
            for row in runs
            if row.get("planner") and row.get("signature")
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
        "prompt_fingerprints": {
            "planner_sha256": hashlib.sha256(PLANNER_SYSTEM.encode("utf-8")).hexdigest(),
            "critic_sha256": hashlib.sha256(CRITIC_SYSTEM.encode("utf-8")).hexdigest(),
        },
        "summary": {
            "cases": len(cases),
            "repetitions": config.repetitions,
            "attempts": attempts,
            "planner_passes": planner_passes,
            "critic_passes": critic_passes,
            "overall_passes": overall_passes,
        },
        "case_results": case_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", ""))
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--reasoning-effort", choices=("none", "low", "medium", "high"), default="low")
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--max-output-tokens", type=int, default=2500)
    parser.add_argument("--no-critic", action="store_true")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args()

    if not args.model.strip():
        raise SystemExit("Provide --model or OPENAI_MODEL")

    config = RunConfig(
        model=args.model.strip(),
        repetitions=args.repetitions,
        reasoning_effort=args.reasoning_effort,
        timeout_seconds=args.timeout_seconds,
        max_output_tokens=args.max_output_tokens,
        critic_enabled=not args.no_critic,
    )
    validate_contract("run_config.schema.json", config.model_dump())
    cases = read_cases(args.cases)
    started = utc_now()
    run_id = args.run_id.strip() or (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", run_id):
        raise SystemExit("run-id may contain only letters, numbers, underscore and hyphen")
    run_dir = (RESULTS_ROOT / run_id).resolve()
    if not run_dir.is_relative_to(RESULTS_ROOT.resolve()):
        raise SystemExit("run output escaped the isolated results directory")
    all_runs: dict[str, list[dict[str, Any]]] = {case.id: [] for case in cases}

    # Persist after every attempt. An interrupted run still leaves inspectable evidence.
    for case in cases:
        for repetition in range(1, config.repetitions + 1):
            record = run_one(case, config, repetition)
            all_runs[case.id].append(record)
            write_json(run_dir / "cases" / case.id / f"r{repetition:02d}.json", record)
            partial = build_payload(
                run_id=run_id,
                started_at=started,
                completed_at=utc_now(),
                config=config,
                source_cases=args.cases,
                cases=cases,
                all_runs=all_runs,
            )
            validate_contract("run_record.schema.json", partial)
            write_json(run_dir / "run.json", partial)
            (run_dir / "SUMMARY.md").write_text(markdown_summary(partial), encoding="utf-8")
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
        source_cases=args.cases,
        cases=cases,
        all_runs=all_runs,
    )
    validate_contract("run_record.schema.json", final)
    write_json(run_dir / "run.json", final)
    (run_dir / "SUMMARY.md").write_text(markdown_summary(final), encoding="utf-8")
    print(json.dumps(final["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
