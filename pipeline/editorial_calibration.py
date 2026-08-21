from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

JUDGE_KEYS = {
    "editorial": "editorial",
    "seo": "seo_master",
    "attention": "youtube_attention_master",
    "voice": "voice_humanity",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_calibration_report(cases_path: Path) -> dict[str, Any]:
    payload = _read_json(cases_path)
    cases = payload.get("cases", []) if isinstance(payload, dict) else []
    base = cases_path.parent.parent.parent
    normalized: list[dict[str, Any]] = []
    for case in cases:
        reviews_path = base / str(case["reviews_path"])
        script_path = base / str(case["script_path"])
        reviews = _read_json(reviews_path)
        if not script_path.exists() or not script_path.read_text(encoding="utf-8").strip():
            raise ValueError(f"Missing regression script: {script_path}")
        human_publishable = bool(case.get("human", {}).get("publishable", False))
        judge_approvals = {
            short: bool(reviews.get(key, {}).get("approved", False))
            for short, key in JUDGE_KEYS.items()
        }
        normalized.append({
            "case_id": case.get("case_id"),
            "human_publishable": human_publishable,
            "judge_approvals": judge_approvals,
            "model": case.get("model", ""),
            "voice_dimensions": {
                name: reviews.get("voice_humanity", {}).get(name)
                for name in ("voice_fidelity", "intellectual_depth", "human_relevance", "analogy_quality")
            },
        })

    total = len(normalized)
    positives = sum(1 for item in normalized if item["human_publishable"])
    negatives = total - positives
    judge_metrics: dict[str, Any] = {}
    for short in JUDGE_KEYS:
        agreement = sum(
            1
            for item in normalized
            if item["judge_approvals"][short] == item["human_publishable"]
        )
        false_accepts = sum(
            1
            for item in normalized
            if not item["human_publishable"] and item["judge_approvals"][short]
        )
        judge_metrics[short] = {
            "agreement_rate": round(agreement / total, 4) if total else None,
            "false_accept_count": false_accepts,
            "false_accept_rate_on_human_rejects": round(false_accepts / negatives, 4) if negatives else None,
        }

    pair_agreement: dict[str, float | None] = {}
    judge_names = list(JUDGE_KEYS)
    for index, left in enumerate(judge_names):
        for right in judge_names[index + 1 :]:
            same = sum(
                1
                for item in normalized
                if item["judge_approvals"][left] == item["judge_approvals"][right]
            )
            pair_agreement[f"{left}__{right}"] = round(same / total, 4) if total else None

    minimum_total = 5
    minimum_positive = 2
    minimum_negative = 2
    ready = total >= minimum_total and positives >= minimum_positive and negatives >= minimum_negative
    return {
        "schema_version": 1,
        "case_count": total,
        "human_publishable_count": positives,
        "human_reject_count": negatives,
        "models_observed": sorted({item["model"] for item in normalized if item["model"]}),
        "judge_metrics": judge_metrics,
        "judge_pair_approval_agreement": pair_agreement,
        "calibration_readiness": {
            "ready_for_dimension_thresholds": ready,
            "ready_for_judge_model_diversification_decision": ready,
            "minimum_total": minimum_total,
            "minimum_human_publishable": minimum_positive,
            "minimum_human_reject": minimum_negative,
            "reason": (
                "Balanced human labels are sufficient for calibration"
                if ready
                else "Collect more human-labeled full scripts, including at least two publishable examples, before activating deterministic voice-dimension floors or changing judge models"
            ),
        },
        "policy": {
            "voice_dimension_thresholds_active": False,
            "judge_model_diversification_active": False,
            "premature_threshold_changes_forbidden": not ready,
        },
        "cases": normalized,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure human-vs-judge editorial calibration")
    parser.add_argument("--cases", default="evals/editorial/cases.json")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    report = build_calibration_report(Path(args.cases))
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
