from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.local.config import (
    DEFAULT_PRIVATE_CONFIG,
    REPO_ROOT,
    initialize_private_config,
    load_config,
)
from pipeline.local.jobs import IMPLEMENTED_OPERATIONS, read_job, run_job
from pipeline.local.preflight import build_preflight
from pipeline.local.staging import load_staged_job, stage_request
from pipeline.local.status import build_status
from pipeline.local.toolchain import build_toolchain
from pipeline.schema_validation import validate_payload


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.local",
        description="AI News Daily local Windows editing harness",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create .local/local_config.json from the committed example")
    init.add_argument("--force", action="store_true")

    doctor = sub.add_parser("doctor", help="Probe the local editing toolchain")
    doctor.add_argument("--config", default=str(DEFAULT_PRIVATE_CONFIG))
    doctor.add_argument("--resolve", action="store_true")
    doctor.add_argument("--deep", action="store_true")
    doctor.add_argument("--otio-smoke", action="store_true")
    doctor.add_argument("--json-out", default=".local/preflight.latest.json")

    sub.add_parser("operations", help="List allowlisted local operations")
    sub.add_parser("status", help="Show local preflight, staged jobs, requests and receipts")

    toolchain = sub.add_parser("toolchain", help="Snapshot local tool versions without absolute paths")
    toolchain.add_argument("--config", default=str(DEFAULT_PRIVATE_CONFIG))
    toolchain.add_argument("--resolve", action="store_true")
    toolchain.add_argument("--json-out", default=".local/toolchain.latest.json")

    stage = sub.add_parser("stage-request", help="Copy a committed repo request into the private staged queue")
    stage.add_argument("request")

    staged = sub.add_parser("run-staged", help="Dry-run or execute one private staged job")
    staged.add_argument("job_id")
    staged.add_argument("--config", default=str(DEFAULT_PRIVATE_CONFIG))
    staged.add_argument("--execute", action="store_true")

    validate = sub.add_parser("validate-job", help="Validate a declarative local job")
    validate.add_argument("job")

    run = sub.add_parser("run-job", help="Dry-run or execute one validated local job")
    run.add_argument("job")
    run.add_argument("--config", default=str(DEFAULT_PRIVATE_CONFIG))
    run.add_argument("--execute", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "init":
        path = initialize_private_config(force=args.force)
        print(json.dumps({"config": str(path), "created_or_present": True}, indent=2))
        return
    if args.command == "operations":
        print(json.dumps({"operations": list(IMPLEMENTED_OPERATIONS)}, indent=2))
        return
    if args.command == "status":
        print(json.dumps(build_status(repo_root=REPO_ROOT), ensure_ascii=False, indent=2))
        return
    if args.command == "stage-request":
        staged_job, stage_meta, payload = stage_request(Path(args.request), repo_root=REPO_ROOT)
        print(json.dumps({"staged_job": str(staged_job.relative_to(REPO_ROOT)), "stage_metadata": str(stage_meta.relative_to(REPO_ROOT)), "sha256": payload["request_sha256"]}, indent=2))
        return
    if args.command == "validate-job":
        payload = read_job(Path(args.job))
        validate_payload(payload, "local/local_job.schema.json")
        print(json.dumps(
            {"valid": True, "job_id": payload["job_id"], "operation": payload["operation"]},
            indent=2,
        ))
        return

    config = load_config(Path(args.config))
    if args.command == "toolchain":
        payload = build_toolchain(config, repo_root=REPO_ROOT, probe_resolve=args.resolve)
        output = Path(args.json_out)
        if not output.is_absolute():
            output = (REPO_ROOT / output).resolve()
        _write_json(output, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if args.command == "run-staged":
        job, meta = load_staged_job(args.job_id, repo_root=REPO_ROOT)
        payload = run_job(job, config, repo_root=REPO_ROOT, execute=args.execute)
        payload["staged_request_sha256"] = meta["request_sha256"]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        raise SystemExit(0 if payload["status"] in {"dry_run", "success"} else 3)
    if args.command == "doctor":
        payload = build_preflight(
            config,
            repo_root=REPO_ROOT,
            require_resolve=args.resolve or args.otio_smoke,
            deep=args.deep,
            otio_smoke=args.otio_smoke,
        )
        output = Path(args.json_out)
        if not output.is_absolute():
            output = (REPO_ROOT / output).resolve()
        _write_json(output, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        raise SystemExit(0 if payload["status"] in {"pass", "warn"} else 2)

    if args.command == "run-job":
        if args.execute:
            raise RuntimeError("Direct execution from a repo JSON is disabled. Use stage-request then run-staged --execute.")
        job = read_job(Path(args.job))
        payload = run_job(job, config, repo_root=REPO_ROOT, execute=False)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        raise SystemExit(0 if payload["status"] in {"dry_run", "success"} else 3)


if __name__ == "__main__":
    main()
