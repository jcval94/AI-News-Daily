from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def evaluate_dense_media_handoff(
    *,
    manifest: list[dict[str, Any]],
    plan: dict[str, Any],
    budget: int,
    minimum_opening_assets: int = 5,
    production_floor: int = 45,
    minimum_unique_ratio: float = 0.65,
    minimum_timeline_reach: float = 0.85,
) -> dict[str, Any]:
    count = len([item for item in manifest if isinstance(item, dict)])
    opening = sum(
        1
        for item in manifest
        if isinstance(item, dict)
        and float(item.get("start_seconds", 0) or 0) < 20
    )
    deduplication = plan.get("deduplication", {})
    if not isinstance(deduplication, dict):
        deduplication = {}
    removed = int(deduplication.get("removed_count", 0) or 0)
    attempted = count + max(0, removed)
    candidate_slots = int(plan.get("candidate_slot_count", 0) or 0)
    target_slots = min(max(0, budget), candidate_slots) if candidate_slots > 0 else max(0, budget)
    timeline_reach = float(plan.get("coverage_ratio", 0.0) or 0.0)

    required_attempted = 0
    required_unique = 0
    if budget >= production_floor:
        required_attempted = min(production_floor, target_slots or production_floor)
        required_unique = min(
            production_floor,
            max(30, math.ceil((target_slots or production_floor) * minimum_unique_ratio)),
        )

    blockers: list[str] = []
    if required_attempted and attempted < required_attempted:
        blockers.append(
            f"attempted_density:{attempted}<{required_attempted}"
        )
    if required_unique and count < required_unique:
        blockers.append(
            f"unique_density:{count}<{required_unique}"
        )
    if opening < minimum_opening_assets:
        blockers.append(
            f"opening_density:{opening}<{minimum_opening_assets}"
        )
    if timeline_reach < minimum_timeline_reach:
        blockers.append(
            f"timeline_reach:{timeline_reach:.4f}<{minimum_timeline_reach:.4f}"
        )

    return {
        "schema_version": 1,
        "ready": not blockers,
        "blockers": blockers,
        "asset_count": count,
        "deduplicated_assets_removed": removed,
        "attempted_asset_count": attempted,
        "opening_media_count": opening,
        "candidate_slot_count": candidate_slots,
        "budget": budget,
        "required_attempted_assets": required_attempted,
        "required_unique_assets": required_unique,
        "minimum_unique_ratio": minimum_unique_ratio,
        "timeline_reach_ratio": round(timeline_reach, 4),
        "minimum_timeline_reach": minimum_timeline_reach,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate post-dedup dense multimedia handoff quality"
    )
    parser.add_argument("--media-dir", required=True)
    parser.add_argument("--budget", type=int, required=True)
    parser.add_argument("--output", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.media_dir)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, list):
        raise SystemExit("manifest.json must contain a list")
    if not isinstance(plan, dict):
        raise SystemExit("plan.json must contain an object")

    report = evaluate_dense_media_handoff(
        manifest=manifest,
        plan=plan,
        budget=max(0, args.budget),
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    print(rendered, end="")
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    if not report["ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
