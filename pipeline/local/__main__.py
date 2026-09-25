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
    if args.command == "validate-job":
        payload = read_job(Path(args.job))
        validate_payload(payload, "local/local_job.schema.json")
        print(json.dumps(
            {"valid": True, "job_id": payload["job_id"], "operation": payload["operation"]},
            indent=2,
        ))
        return

    config = load_config(Path(args.config))
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
        job = read_job(Path(args.job))
        payload = run_job(job, config, repo_root=REPO_ROOT, execute=args.execute)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        raise SystemExit(0 if payload["status"] in {"dry_run", "success"} else 3)


if __name__ == "__main__":
    main()
