"""Adversarial stress harness for multimedia retrieval.

Default mode validates the case corpus and scoring logic without network/model calls.
Use --live to exercise the real semantic planners, catalogue discovery and relevance
assessment. Live mode intentionally does not hide failures: the report distinguishes
semantic resolution, candidate discovery and candidate selection.

Existing Media Integration Staging remains the materialization/readiness test. This
harness answers an earlier question: did we understand and retrieve the right thing?
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from pipeline.media_acquisition import IMAGE_SOURCES, VIDEO_SOURCES, need_description
from pipeline.media_sources.image_search import model as image_model
from pipeline.media_sources.image_search import sources as image_sources
from pipeline.media_sources.video_search import run as video_run

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = Path(__file__).with_name("cases.json")


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[^\W_]+", text, flags=re.UNICODE))


def contains_any(text: str, terms: list[str]) -> bool:
    haystack = " " + normalize(text) + " "
    return any(" " + normalize(term) + " " in haystack for term in terms if normalize(term))


def compact_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    metadata = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
    return {
        "key": candidate.get("key"),
        "source": candidate.get("source"),
        "id": candidate.get("id"),
        "title": candidate.get("title") or metadata.get("title", ""),
        "description": (candidate.get("description") or metadata.get("description", ""))[:1200],
        "creator": candidate.get("creator") or metadata.get("creator", ""),
        "license": candidate.get("license") or metadata.get("license", ""),
        "width": candidate.get("width"),
        "height": candidate.get("height"),
        "duration_seconds": candidate.get("duration_seconds"),
        "url": candidate.get("url", ""),
    }


def candidate_text(candidate: dict[str, Any]) -> str:
    metadata = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
    parts = [
        candidate.get("title", ""),
        candidate.get("description", ""),
        metadata.get("title", ""),
        metadata.get("description", ""),
        metadata.get("subjects", ""),
        metadata.get("tags", ""),
    ]
    return " ".join(str(part) for part in parts if part)


def request_json(url: str, **kwargs: Any) -> dict[str, Any]:
    return image_sources.request_json(url, **kwargs)


def load_cases(path: Path, profile: str) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("cases"), list):
        raise ValueError("Unsupported multimedia stress corpus")
    selected = []
    seen = set()
    for case in payload["cases"]:
        required = {
            "id", "profile", "category", "severity", "narration", "subject", "visual_query",
            "kinds", "expected_mode", "semantic_terms_any", "forbidden_terms",
            "may_be_rights_blocked", "note",
        }
        missing = sorted(required - set(case))
        if missing:
            raise ValueError(f"{case.get('id', '<unknown>')}: missing fields {missing}")
        if case["id"] in seen:
            raise ValueError(f"Duplicate case id: {case['id']}")
        seen.add(case["id"])
        if case["expected_mode"] not in {"exact", "context", "refuse_ambiguity"}:
            raise ValueError(f"{case['id']}: invalid expected_mode")
        if not set(case["kinds"]).issubset({"image", "video"}) or not case["kinds"]:
            raise ValueError(f"{case['id']}: invalid kinds")
        if case["expected_mode"] != "refuse_ambiguity" and normalize(case["subject"]) not in normalize(case["narration"]):
            raise ValueError(f"{case['id']}: subject must be grounded literally in narration")
        if profile in case["profile"]:
            selected.append(case)
    if not selected:
        raise ValueError(f"No cases selected for profile={profile}")
    return selected


def make_need(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "need_id": case["id"],
        "subject": case["subject"],
        "period": case.get("period", ""),
        "geography": case.get("geography", ""),
        "visual_queries": [case["visual_query"]],
        "slots": [1],
        "grounded": True,
    }


def summarize_match(case: dict[str, Any], plan_text: str, selected: list[dict[str, Any]]) -> dict[str, Any]:
    selected_blob = "\n".join(candidate_text(item) for item in selected)
    semantic_terms = list(case.get("semantic_terms_any") or [])
    forbidden = list(case.get("forbidden_terms") or [])
    plan_resolved = True if not semantic_terms else contains_any(plan_text, semantic_terms)
    selected_resolved = True if not semantic_terms else contains_any(selected_blob, semantic_terms)
    forbidden_hit = contains_any(selected_blob, forbidden) if forbidden else False

    if case["expected_mode"] == "refuse_ambiguity":
        return {
            "plan_resolved": plan_resolved,
            "selected_resolved": selected_resolved,
            "forbidden_hit": forbidden_hit,
            "pass": False,
            "status": "NEEDS_AMBIGUITY_REFUSAL",
        }

    if forbidden_hit:
        status = "FAIL_WRONG_ENTITY"
        passed = False
    elif selected and selected_resolved:
        status = "PASS_SELECTED"
        passed = True
    elif plan_resolved:
        status = "SEMANTIC_ONLY"
        # Semantic resolution is useful evidence, but the user's retrieval goal was
        # not met. Rights/provider constraints explain the degradation; they do not
        # turn a missing exact asset into a successful retrieval.
        passed = False
    else:
        status = "FAIL_NO_RESOLUTION"
        passed = False
    return {
        "plan_resolved": plan_resolved,
        "selected_resolved": selected_resolved,
        "forbidden_hit": forbidden_hit,
        "pass": passed,
        "status": status,
    }


def run_image(case: dict[str, Any]) -> dict[str, Any]:
    need = make_need(case)
    description = need_description(need)
    result: dict[str, Any] = {"kind": "image", "status": "started", "selected": []}
    try:
        plan, meta = image_model.make_plan(description, request_json)
    except Exception as error:
        message = str(error)
        ambiguous = "ambiguous" in message.casefold()
        if case["expected_mode"] == "refuse_ambiguity" and ambiguous:
            result.update(status="PASS_AMBIGUITY_REFUSED", passed=True, error=message)
        else:
            result.update(status="PLANNER_ERROR", passed=False, error=message)
        return result

    result["plan"] = plan.model_dump()
    result["planner_meta"] = meta
    plan_text = json.dumps(result["plan"], ensure_ascii=False)

    if case["expected_mode"] == "refuse_ambiguity":
        result.update(status="FAIL_AMBIGUITY_ACCEPTED", passed=False)
        return result

    try:
        try:
            entity = image_sources.resolve_entity(plan)
        except Exception as error:
            entity = {"status": "unavailable", "reason": str(error)}
        candidates, discovery = image_sources.discover(plan, IMAGE_SOURCES, entity)
        decisions, assess_meta = image_model.assess(plan, candidates, entity, request_json, editorial_pack=True)
        selected = []
        for candidate in candidates:
            decision = decisions.get(candidate.get("key"))
            if decision and decision.get("relevance") == "direct":
                selected.append({**candidate, "_decision": decision})
        match = summarize_match(case, plan_text, selected)
        result.update(
            status=match["status"],
            passed=match["pass"],
            match=match,
            entity=entity,
            discovery=discovery,
            candidate_count=len(candidates),
            selected_count=len(selected),
            selected=[compact_candidate(item) | {"decision": item["_decision"]} for item in selected[:12]],
            assessment_meta=assess_meta,
        )
    except Exception as error:
        result.update(status="DISCOVERY_OR_ASSESSMENT_ERROR", passed=False, error=str(error))
    return result


def run_video(case: dict[str, Any]) -> dict[str, Any]:
    need = make_need(case)
    description = need_description(need)
    result: dict[str, Any] = {"kind": "video", "status": "started", "selected": []}
    try:
        plan, meta = video_run.make_plan(description, "semantic", request_json)
        result["plan"] = plan.model_dump()
        result["planner_meta"] = meta
        plan_text = json.dumps(result["plan"], ensure_ascii=False)

        if case["expected_mode"] == "refuse_ambiguity":
            # Video planner has no explicit unambiguous bit. An ambiguous case is considered safely
            # refused only when it does not establish a required identity and selects nothing.
            candidates, discovery = video_run.discover(plan, VIDEO_SOURCES)
            assessment = video_run.assess_candidates(plan, candidates, request_json)
            selected = [item for item in candidates if item.get("relevant")]
            safe_refusal = plan.required_identity is None and not selected
            result.update(
                status="PASS_AMBIGUITY_REFUSED" if safe_refusal else "FAIL_AMBIGUITY_ACCEPTED",
                passed=safe_refusal,
                discovery=discovery,
                assessment=assessment,
                candidate_count=len(candidates),
                selected_count=len(selected),
                selected=[compact_candidate(item) for item in selected[:12]],
            )
            return result

        candidates, discovery = video_run.discover(plan, VIDEO_SOURCES)
        assessment = video_run.assess_candidates(plan, candidates, request_json)
        selected = [item for item in candidates if item.get("relevant")]
        match = summarize_match(case, plan_text, selected)
        risk_flags = []
        if case["category"] == "video_clip_offset":
            long_selected = [item for item in selected if float(item.get("duration_seconds") or 0) > 30]
            if long_selected:
                risk_flags.append("CURRENT_PIPELINE_CLIPS_FROM_ZERO_0_30S")
        if case["category"] == "video_metadata_visual_mismatch" and selected:
            risk_flags.append("METADATA_RELEVANCE_WITHOUT_FRAME_LEVEL_VISUAL_PROOF")
        result.update(
            status=match["status"],
            passed=match["pass"],
            match=match,
            discovery=discovery,
            assessment=assessment,
            candidate_count=len(candidates),
            selected_count=len(selected),
            selected=[compact_candidate(item) for item in selected[:12]],
            risk_flags=risk_flags,
        )
    except Exception as error:
        result.update(status="PLANNER_DISCOVERY_OR_ASSESSMENT_ERROR", passed=False, error=str(error))
    return result


def case_result(case: dict[str, Any], *, live: bool) -> dict[str, Any]:
    result = {
        "id": case["id"],
        "category": case["category"],
        "severity": case["severity"],
        "expected_mode": case["expected_mode"],
        "subject": case["subject"],
        "visual_query": case["visual_query"],
        "note": case["note"],
        "live": live,
        "kinds": [],
    }
    if not live:
        result["passed"] = True
        result["status"] = "CORPUS_VALID"
        return result

    for kind in case["kinds"]:
        result["kinds"].append(run_image(case) if kind == "image" else run_video(case))
    passed = all(item.get("passed", False) for item in result["kinds"])
    result["passed"] = passed
    result["status"] = "PASS" if passed else "FAIL"
    return result


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    lines = [
        "# Multimedia retrieval stress report",
        "",
        f"- profile: `{payload['profile']}`",
        f"- mode: `{'live' if payload['live'] else 'deterministic-corpus'}`",
        f"- cases: **{summary['cases']}**",
        f"- passed: **{summary['passed']}**",
        f"- failed: **{summary['failed']}**",
        "",
        "| Case | Category | Severity | Status | Kind detail |",
        "|---|---|---:|---|---|",
    ]
    for row in payload["results"]:
        details = ", ".join(
            f"{item.get('kind')}:{item.get('status')}"
            + (f" ({item.get('selected_count', 0)} selected)" if "selected_count" in item else "")
            for item in row.get("kinds", [])
        ) or "corpus validation"
        lines.append(
            f"| {row['id']} | {row['category']} | {row['severity']} | {row['status']} | {details} |"
        )
    lines.extend([
        "",
        "## Failure taxonomy",
        "",
    ])
    for status, count in sorted(summary["kind_statuses"].items()):
        lines.append(f"- `{status}`: {count}")
    lines.extend([
        "",
        "## Interpretation",
        "",
        "- PASS_SELECTED: at least one semantically matching candidate survived relevance selection.",
        "- SEMANTIC_ONLY: the planner resolved the intended identity but no matching selected candidate was available; this only counts as pass for cases explicitly marked as rights/provider constrained.",
        "- FAIL_WRONG_ENTITY: a forbidden collision survived selection.",
        "- FAIL_NO_RESOLUTION: even the generated search plan did not express the intended identity.",
        "- PASS_AMBIGUITY_REFUSED: the system failed closed instead of guessing.",
        "",
        "This report intentionally stops before final materialization. Media Integration Staging remains the independent download/license/decode/readiness test.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--profile", choices=("core", "full"), default="core")
    parser.add_argument("--live", action="store_true", help="Exercise model-backed planning and live providers.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", type=Path, default=Path("experiments/media_retrieval_stress/results/latest.json"))
    parser.add_argument("--enforce", action="store_true", help="Exit non-zero when any selected case fails.")
    args = parser.parse_args()

    cases = load_cases(args.cases, args.profile)
    if args.limit > 0:
        cases = cases[: args.limit]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    def persist(*, complete: bool) -> dict[str, Any]:
        kind_statuses = Counter(
            item.get("status", "UNKNOWN")
            for row in results
            for item in row.get("kinds", [])
        )
        passed = sum(bool(row.get("passed")) for row in results)
        payload = {
            "schema_version": 1,
            "profile": args.profile,
            "live": args.live,
            "complete": complete,
            "summary": {
                "cases": len(results),
                "planned_cases": len(cases),
                "passed": passed,
                "failed": len(results) - passed,
                "remaining": len(cases) - len(results),
                "kind_statuses": dict(kind_statuses),
            },
            "results": results,
        }
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(args.output.with_suffix(".md"), payload)
        return payload

    payload = persist(complete=False)
    for index, case in enumerate(cases, 1):
        result = case_result(case, live=args.live)
        results.append(result)
        payload = persist(complete=index == len(cases))
        print(
            f"[{index}/{len(cases)}] {case['id']}: {result['status']}",
            flush=True,
        )

    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    if args.enforce and payload["summary"]["passed"] != len(results):
        raise SystemExit("Multimedia retrieval stress suite has failing cases; inspect the report.")


if __name__ == "__main__":
    main()
