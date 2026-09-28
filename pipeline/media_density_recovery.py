from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from pipeline.media_density_gate import evaluate_dense_media_handoff


def recommend_recovery_budget(
    report: dict[str, Any],
    *,
    current_attempt_budget: int,
    max_extra_attempts: int = 12,
    safety_margin: int = 2,
) -> int | None:
    """Recommend one bounded retry only for post-dedup unique-density loss.

    The delivery contract is not relaxed. We simply sample a few additional storyboard
    slots when the first pass proves that duplicates consumed too much of the acquisition
    budget. Any opening/timeline/underproduction blocker remains a hard failure.
    """
    blockers = [str(item) for item in report.get("blockers", [])]
    if report.get("ready") or not blockers:
        return None
    if any(not item.startswith("unique_density:") for item in blockers):
        return None

    required = int(report.get("required_unique_assets", 0) or 0)
    unique = int(report.get("asset_count", 0) or 0)
    attempted = int(report.get("attempted_asset_count", 0) or 0)
    candidate_slots = int(report.get("candidate_slot_count", 0) or 0)
    current = max(int(current_attempt_budget or 0), attempted)

    if required <= unique or current <= 0 or candidate_slots <= current:
        return None

    retention = unique / attempted if attempted > 0 else 0.0
    # Avoid extreme retry sizes from pathological first passes. The retry is deliberately
    # bounded; if it still cannot satisfy the unchanged gate, production remains blocked.
    conservative_retention = min(1.0, max(0.35, retention))
    estimated = math.ceil(required / conservative_retention) + max(0, safety_margin)
    missing = required - unique
    minimum_growth = current + missing + max(0, safety_margin)
    hard_cap = min(candidate_slots, current + max(0, max_extra_attempts))
    next_budget = min(hard_cap, max(current + 1, estimated, minimum_growth))
    return next_budget if next_budget > current else None


def recovery_report(
    *,
    media_dir: Path,
    delivery_budget: int,
    max_extra_attempts: int = 12,
) -> dict[str, Any]:
    manifest = json.loads((media_dir / "manifest.json").read_text(encoding="utf-8"))
    plan = json.loads((media_dir / "plan.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, list):
        raise ValueError("manifest.json must contain a list")
    if not isinstance(plan, dict):
        raise ValueError("plan.json must contain an object")

    gate = evaluate_dense_media_handoff(
        manifest=manifest,
        plan=plan,
        budget=max(0, delivery_budget),
    )
    current_attempt_budget = int(
        plan.get("max_media_downloads", gate.get("attempted_asset_count", 0)) or 0
    )
    retry_budget = recommend_recovery_budget(
        gate,
        current_attempt_budget=current_attempt_budget,
        max_extra_attempts=max_extra_attempts,
    )
    return {
        "schema_version": 1,
        "delivery_budget": max(0, delivery_budget),
        "current_attempt_budget": current_attempt_budget,
        "retry_budget": retry_budget,
        "gate": gate,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recommend a bounded second dense-media acquisition pass after dedup loss"
    )
    parser.add_argument("--media-dir", required=True)
    parser.add_argument("--delivery-budget", type=int, required=True)
    parser.add_argument("--max-extra-attempts", type=int, default=12)
    parser.add_argument("--value-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = recovery_report(
        media_dir=Path(args.media_dir),
        delivery_budget=args.delivery_budget,
        max_extra_attempts=max(0, args.max_extra_attempts),
    )
    if args.value_only:
        value = report.get("retry_budget")
        print("" if value is None else int(value))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
