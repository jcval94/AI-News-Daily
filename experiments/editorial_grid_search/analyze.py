from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
DEFAULT_RESULTS = HERE / "results"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def balanced_score(evaluation: dict[str, Any]) -> float:
    score = (
        0.30 * float(evaluation["editorial_score"])
        + 0.30 * float(evaluation["voice_score"])
        + 0.25 * float(evaluation["attention_score"])
        + 0.15 * float(evaluation["seo_score"])
    )
    factual_penalty = {"low": 0.0, "medium": 0.35, "high": 1.0}.get(
        str(evaluation.get("factuality_risk", "")).lower(), 1.0
    )
    smell_penalty = {"low": 0.0, "medium": 0.35, "high": 0.8}.get(
        str(evaluation.get("ai_smell_risk", "")).lower(), 0.8
    )
    return round(max(0.0, min(10.0, score - factual_penalty - smell_penalty)), 4)


def mean(values: list[float]) -> float:
    return round(statistics.mean(values), 4) if values else 0.0


def stdev(values: list[float]) -> float:
    return round(statistics.stdev(values), 4) if len(values) > 1 else 0.0


def load_records(results_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ok: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for path in sorted((results_root / "raw").glob("*/*.json")):
        payload = read_json(path)
        payload["_path"] = str(path)
        if payload.get("status") == "ok" and isinstance(payload.get("evaluation"), dict):
            payload["balanced_score"] = balanced_score(payload["evaluation"])
            ok.append(payload)
        else:
            errors.append(payload)
    return ok, errors


def aggregate_configs(
    records: list[dict[str, Any]],
    configs: dict[str, dict[str, Any]],
    expected_folds: int,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[str(row["config"]["id"])].append(row)

    summary: list[dict[str, Any]] = []
    for config_id, config in configs.items():
        rows = grouped.get(config_id, [])
        scores = [float(row["balanced_score"]) for row in rows]
        evs = [row["evaluation"] for row in rows]
        summary.append(
            {
                "config_id": config_id,
                "label": config.get("label", ""),
                "folds_complete": len(rows),
                "expected_folds": expected_folds,
                "complete": len(rows) == expected_folds,
                "balanced_mean": mean(scores),
                "balanced_std": stdev(scores),
                "balanced_worst": round(min(scores), 4) if scores else 0.0,
                "editorial_mean": mean([float(ev["editorial_score"]) for ev in evs]),
                "attention_mean": mean([float(ev["attention_score"]) for ev in evs]),
                "voice_mean": mean([float(ev["voice_score"]) for ev in evs]),
                "seo_mean": mean([float(ev["seo_score"]) for ev in evs]),
                "opening_fit_mean": mean([float(ev["opening_fit"]) for ev in evs]),
                "first_evidence_mean": mean(
                    [float(ev["first_evidence_effectiveness"]) for ev in evs]
                ),
                "narrative_motion_mean": mean(
                    [float(ev["narrative_motion"]) for ev in evs]
                ),
                "thesis_evolution_mean": mean(
                    [float(ev["thesis_evolution"]) for ev in evs]
                ),
                "evidence_density_mean": mean(
                    [float(ev["evidence_density"]) for ev in evs]
                ),
                "factuality_low_rate": mean(
                    [
                        1.0 if str(ev.get("factuality_risk")) == "low" else 0.0
                        for ev in evs
                    ]
                ),
                "ai_smell_low_rate": mean(
                    [
                        1.0 if str(ev.get("ai_smell_risk")) == "low" else 0.0
                        for ev in evs
                    ]
                ),
                "word_count_mean": mean(
                    [float(row.get("script_word_count", 0)) for row in rows]
                ),
            }
        )

    summary.sort(
        key=lambda item: (
            bool(item["complete"]),
            float(item["balanced_mean"]),
            float(item["balanced_worst"]),
            float(item["voice_mean"]),
            float(item["attention_mean"]),
        ),
        reverse=True,
    )
    for rank, item in enumerate(summary, start=1):
        item["rank"] = rank
    return summary


def factor_effects(
    records: list[dict[str, Any]], factor_keys: list[str]
) -> list[dict[str, Any]]:
    fold_scores: dict[str, list[float]] = defaultdict(list)
    for row in records:
        fold_scores[str(row["fold"]["id"])].append(float(row["balanced_score"]))
    fold_means = {
        fold: statistics.mean(values)
        for fold, values in fold_scores.items()
        if values
    }

    centered_groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    raw_groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in records:
        fold_id = str(row["fold"]["id"])
        centered = float(row["balanced_score"]) - float(fold_means.get(fold_id, 0))
        config = row["config"]
        for key in factor_keys:
            value = json.dumps(config.get(key), ensure_ascii=False, sort_keys=True)
            centered_groups[(key, value)].append(centered)
            raw_groups[(key, value)].append(float(row["balanced_score"]))

    effects: list[dict[str, Any]] = []
    for (factor, value), values in centered_groups.items():
        effects.append(
            {
                "factor": factor,
                "value": value,
                "n": len(values),
                "fold_centered_delta": round(statistics.mean(values), 4),
                "raw_balanced_mean": round(
                    statistics.mean(raw_groups[(factor, value)]), 4
                ),
            }
        )
    effects.sort(
        key=lambda row: (row["factor"], -float(row["fold_centered_delta"]))
    )
    return effects


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def render_results(
    summary: list[dict[str, Any]],
    effects: list[dict[str, Any]],
    records: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    expected_total: int,
) -> str:
    baseline = next(
        (row for row in summary if row["config_id"] == "g00_current_like"), None
    )
    baseline_score = float(baseline["balanced_mean"]) if baseline else 0.0

    lines = [
        "# Editorial Grid Search — Results",
        "",
        f"Completed scripts: **{len(records)}/{expected_total}**.",
        "",
        "Ranking is cross-validated across three time-separated news folds. "
        "Balanced score = 0.30 Editorial + 0.30 Voice + 0.25 Attention + 0.15 SEO, "
        "with factuality/AI-smell penalties.",
        "",
        "## Configuration ranking",
        "",
        "| Rank | Config | CV score | Δ vs current-like | Worst fold | Editorial | Attention | Voice | SEO | Factual low | AI-smell low |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary:
        delta = float(row["balanced_mean"]) - baseline_score if baseline else 0.0
        lines.append(
            f"| {row['rank']} | {row['config_id']} | "
            f"{float(row['balanced_mean']):.2f} | {delta:+.2f} | "
            f"{float(row['balanced_worst']):.2f} | "
            f"{float(row['editorial_mean']):.2f} | "
            f"{float(row['attention_mean']):.2f} | "
            f"{float(row['voice_mean']):.2f} | "
            f"{float(row['seo_mean']):.2f} | "
            f"{100 * float(row['factuality_low_rate']):.0f}% | "
            f"{100 * float(row['ai_smell_low_rate']):.0f}% |"
        )

    lines += [
        "",
        "## Factor signals",
        "",
        "Effects are fold-centered. Positive means that factor level tended to score "
        "above the mean of the same news fold. Fractional-grid effects are directional, "
        "not isolated causal estimates.",
        "",
    ]

    by_factor: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in effects:
        by_factor[str(row["factor"])].append(row)

    for factor, rows in by_factor.items():
        lines += [
            f"### {factor}",
            "",
            "| Level | N | Fold-centered Δ | Raw mean |",
            "| --- | ---: | ---: | ---: |",
        ]
        for row in sorted(
            rows, key=lambda item: float(item["fold_centered_delta"]), reverse=True
        ):
            lines.append(
                f"| {row['value']} | {row['n']} | "
                f"{float(row['fold_centered_delta']):+.3f} | "
                f"{float(row['raw_balanced_mean']):.3f} |"
            )
        lines.append("")

    if summary:
        best = summary[0]
        lines += [
            "## Promotion guardrail",
            "",
            f"Current top configuration: **{best['config_id']}**. Treat it as provisional "
            "until all 60 scripts are complete and a human spot-check confirms evaluator alignment.",
            "",
            "Prefer the smallest factor-level changes that are robust across folds rather than "
            "copying an entire winning prompt wholesale.",
            "",
        ]

    if errors:
        lines += ["## Failures / incomplete cells", ""]
        for err in errors:
            lines.append(
                f"- {err.get('config', {}).get('id', '?')} / "
                f"{err.get('fold', {}).get('id', '?')}: "
                f"{err.get('error_type', 'error')} — {err.get('error', '')}"
            )
        lines.append("")

    lines += [
        "## Method limitations",
        "",
        "- Three folds measure robustness across content, not random-seed variance.",
        "- The same model family writes and evaluates, so human review remains necessary.",
        "- Factor effects are partially confounded because this is a bounded fractional grid.",
        "- No refinement loop is used; architecture quality is measured before repair.",
        "",
    ]
    return "\n".join(lines)


def analyze(results_root: Path, require_complete: bool) -> int:
    grid = read_json(HERE / "grid.json")
    folds = read_json(HERE / "folds.json")
    configs = {
        str(item["id"]): item
        for item in grid.get("configurations", [])
        if isinstance(item, dict)
    }
    expected_folds = int(grid.get("scripts_per_configuration", 3))
    expected_total = len(configs) * expected_folds

    records, errors = load_records(results_root)
    summary = aggregate_configs(records, configs, expected_folds)
    effects = factor_effects(records, list(grid.get("factor_keys", [])))

    write_csv(results_root / "summary.csv", summary)
    write_csv(results_root / "factor_effects.csv", effects)
    (results_root / "RESULTS.md").write_text(
        render_results(summary, effects, records, errors, expected_total) + "\n",
        encoding="utf-8",
    )

    manifest = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "configuration_count": len(configs),
        "fold_count": len(folds.get("folds", [])),
        "expected_scripts": expected_total,
        "completed_scripts": len(records),
        "error_cells": len(errors),
        "complete": len(records) == expected_total,
    }
    (results_root / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False))
    return 2 if require_complete and len(records) != expected_total else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate editorial grid-search CV results"
    )
    parser.add_argument("--results-root", default=str(DEFAULT_RESULTS))
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    raise SystemExit(analyze(Path(args.results_root), args.require_complete))


if __name__ == "__main__":
    main()
