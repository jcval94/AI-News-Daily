from __future__ import annotations

import argparse
import json
import re
import unicodedata
from copy import deepcopy
from pathlib import Path
from typing import Any

_GENERIC_EVIDENCE_TOKENS = {
    "anchor",
    "benchmark",
    "case",
    "contrast",
    "evidence",
    "example",
    "prediction",
    "predictions",
    "support",
    "tool",
    "tools",
    "use",
    "using",
    "bridge",
    "agent",
    "agents",
    "model",
    "models",
}


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(char for char in text if not unicodedata.combining(char))


def _tokens(value: Any) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", _fold(value).replace("_", " "))
        if len(token) >= 3
    }


def _signal_tokens(evidence_id: str) -> set[str]:
    return {
        token
        for token in _tokens(evidence_id)
        if token not in _GENERIC_EVIDENCE_TOKENS and len(token) >= 4
    }


def _item_tokens(item: dict[str, Any]) -> set[str]:
    return _tokens(
        " ".join(
            str(item.get(key, "") or "")
            for key in ("title", "summary", "category", "why_it_matters")
        )
    )


def reconcile_evidence_indices(
    episode_plan: dict[str, Any], selected_news: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Repair only high-confidence evidence/index mismatches.

    The Director historically selected a valid integer index but could confuse catalog position with
    evidence position. We only override that integer when a distinctive token embedded in evidence_id
    (e.g. `aqpotency`, `aqcat`, `traces`) matches exactly one selected source and the currently declared
    source does not match as well. Generic IDs such as `case_1` are left untouched.
    """
    plan = deepcopy(episode_plan)
    selected_items = [
        item for item in selected_news.get("items", []) if isinstance(item, dict)
    ] if isinstance(selected_news, dict) else []
    tokenized_items = [_item_tokens(item) for item in selected_items]
    changes: list[dict[str, Any]] = []

    for evidence in plan.get("evidence", []) if isinstance(plan, dict) else []:
        if not isinstance(evidence, dict):
            continue
        evidence_id = str(evidence.get("evidence_id", "") or "").strip()
        signals = _signal_tokens(evidence_id)
        if not evidence_id or not signals or not selected_items:
            continue

        try:
            declared = int(evidence.get("selected_news_index", 0) or 0)
        except (TypeError, ValueError):
            declared = 0

        scores = [len(signals & item_tokens) for item_tokens in tokenized_items]
        best_score = max(scores, default=0)
        if best_score <= 0:
            continue
        best_indices = [index + 1 for index, score in enumerate(scores) if score == best_score]
        if len(best_indices) != 1:
            continue
        resolved = best_indices[0]
        declared_score = scores[declared - 1] if 1 <= declared <= len(scores) else 0
        if resolved == declared or declared_score >= best_score:
            continue

        old_title = (
            str(selected_items[declared - 1].get("title", "") or "")
            if 1 <= declared <= len(selected_items)
            else ""
        )
        new_title = str(selected_items[resolved - 1].get("title", "") or "")
        evidence["selected_news_index"] = resolved
        changes.append(
            {
                "evidence_id": evidence_id,
                "declared_selected_news_index": declared,
                "resolved_selected_news_index": resolved,
                "signal_tokens": sorted(signals),
                "declared_title": old_title,
                "resolved_title": new_title,
                "reason": "unique distinctive evidence_id token match",
            }
        )

    plan["evidence_reconciliation"] = {
        "schema_version": 1,
        "changed": bool(changes),
        "changes": changes,
    }
    return plan, changes


def reconcile_episode_dir(episode_dir: Path, *, write: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    plan_path = episode_dir / "episode_plan.json"
    selected_path = episode_dir / "selected_news.json"
    if not plan_path.exists():
        # Canonical episodes created before the essay-first contract have no EpisodePlan.
        # The Review Hub may still render them as legacy history; there is nothing safe to
        # reconcile and we must not synthesize an evidence catalog retroactively.
        return {
            "evidence_reconciliation": {
                "schema_version": 1,
                "changed": False,
                "skipped": True,
                "reason": "legacy artifact has no episode_plan.json",
            }
        }, []
    if not selected_path.exists():
        raise FileNotFoundError(f"Modern episode has episode_plan.json but no {selected_path.name}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    reconciled, changes = reconcile_evidence_indices(plan, selected)
    if write:
        plan_path.write_text(json.dumps(reconciled, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return reconciled, changes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconcile high-confidence evidence/source mismatches in a review artifact")
    parser.add_argument("--episode-dir", required=True)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    reconciled, changes = reconcile_episode_dir(Path(args.episode_dir), write=bool(args.write))
    metadata = reconciled.get("evidence_reconciliation", {}) if isinstance(reconciled, dict) else {}
    print(
        json.dumps(
            {
                "changed_count": len(changes),
                "changes": changes,
                "skipped": bool(metadata.get("skipped", False)),
                "reason": metadata.get("reason", ""),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
