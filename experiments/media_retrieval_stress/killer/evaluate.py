"""Validate and summarize an observed killer retrieval run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator


HERE = Path(__file__).resolve().parent
SCHEMA = HERE / "contracts" / "killer_result.schema.json"
DEFAULT_RESULT = HERE / "results" / "2026-09-28-live-web.json"


def recompute_summary(payload: dict) -> dict:
    cases = payload["cases"]
    return {
        "cases": len(cases),
        "entity_resolution_pass": sum(item["entity_resolution"]["status"] == "pass" for item in cases),
        "exact_discovery_pass": sum(item["exact_discovery"]["status"] == "found_exact" for item in cases),
        "visual_verification_pass": sum(item["visual_verification"]["status"] == "verified" for item in cases),
        "exact_usable": sum(item["final_status"] == "FOUND_EXACT_USABLE" for item in cases),
        "exact_reference_only": sum(item["final_status"] == "FOUND_EXACT_REFERENCE_ONLY" for item in cases),
        "wrong_substitutions": sum(
            item["final_status"] == "FOUND_CONTEXTUAL"
            and item["exact_discovery"]["status"] == "found_exact"
            for item in cases
        ),
        "scene_offsets_resolved": sum(bool(item["visual_verification"].get("scene_intervals")) for item in cases),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, default=DEFAULT_RESULT)
    args = parser.parse_args()

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    payload = json.loads(args.result.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)

    recomputed = recompute_summary(payload)
    if recomputed != payload["summary"]:
        raise SystemExit(
            "summary mismatch\nexpected="
            + json.dumps(recomputed, ensure_ascii=False, indent=2)
            + "\nobserved="
            + json.dumps(payload["summary"], ensure_ascii=False, indent=2)
        )

    bad = [
        item["id"]
        for item in payload["cases"]
        if item["final_status"] in {"NOT_FOUND", "AMBIGUOUS"}
    ]
    print(json.dumps({
        "run_id": payload["run_id"],
        "summary": recomputed,
        "unresolved_cases": bad,
        "pass": not bad and recomputed["wrong_substitutions"] == 0,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
