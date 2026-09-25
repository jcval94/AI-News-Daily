from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

import yaml

from pipeline.media_inspection import inspect_media, safe_repo_path
from pipeline.schema_validation import validate_payload


SCHEMA_VERSION = 1


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object: {path}")
    return payload


def _read_policy(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("asset_readiness.yaml must contain an object")
    return payload


def build_asset_readiness(
    *,
    virtual_timeline: dict[str, Any],
    resolve_plan: dict[str, Any],
    preview_validation: dict[str, Any] | None,
    repo_root: Path,
    policy: dict[str, Any],
) -> dict[str, Any]:
    episode_date = str(virtual_timeline.get("episode_date", "") or "")
    placements = {
        str(item.get("placement_id", "") or ""): item
        for item in resolve_plan.get("placements", [])
        if isinstance(item, dict)
    }
    thresholds = policy.get("thresholds", {})
    quality = policy.get("quality", {})
    critical_roles = {str(x) for x in policy.get("critical_visual_roles", [])}
    fallback_ids = {
        str(item.get("placement_id", "") or "")
        for item in (preview_validation or {}).get("warnings", [])
        if isinstance(item, dict) and item.get("code") == "preview_decode_fallback"
    }

    v2 = next(
        (t for t in virtual_timeline.get("tracks", []) if isinstance(t, dict) and t.get("track_id") == "V2"),
        {"clips": []},
    )
    items: list[dict[str, Any]] = []
    for clip in v2.get("clips", []):
        if not isinstance(clip, dict):
            continue
        clip_id = str(clip.get("clip_id", "") or "")
        placement = placements.get(clip_id, {})
        cue_id = str(clip.get("cue_id", "") or clip_id)
        role = str((clip.get("director", {}) or {}).get("visual_role", "") or "")
        critical = role in critical_roles
        planned = float(clip.get("duration_seconds", 0) or 0)
        placeholder = bool(placement.get("placeholder", clip.get("status") != "resolved"))
        logical = str(placement.get("logical_repo_path", "") or "")
        issues: list[str] = []
        inspection: dict[str, Any] = {}

        if placeholder:
            state = "missing"
            issues.append("unresolved_placeholder")
        else:
            if not logical:
                state = "technical_failure"
                issues.append("missing_logical_path")
            else:
                physical = safe_repo_path(repo_root, logical)
                inspection = inspect_media(physical)
                if not inspection.get("ok"):
                    state = "technical_failure"
                    issues.append(str(inspection.get("error_code", "media_inspection_failed")))
                else:
                    width = int(inspection.get("width", 0) or 0)
                    height = int(inspection.get("height", 0) or 0)
                    short_edge = min(width, height) if width and height else 0
                    if short_edge and short_edge < int(quality.get("min_short_edge_px", 720)):
                        issues.append("low_resolution")
                    if inspection.get("kind") == "video":
                        source_duration = float(inspection.get("duration_seconds", 0) or 0)
                        ratio = source_duration / planned if planned > 0 else 1.0
                        inspection["duration_ratio_vs_planned"] = round(ratio, 4)
                        if ratio < float(quality.get("min_video_duration_ratio", 0.75)):
                            issues.append("source_shorter_than_planned")
                    if clip_id in fallback_ids:
                        issues.append("preview_decode_fallback")
                    license_label = str((clip.get("source", {}) or {}).get("license", "") or "")
                    if not license_label:
                        issues.append("missing_license_label")
                    state = "resolved_degraded" if issues else "resolved_clean"

        items.append({
            "cue_id": cue_id,
            "clip_id": clip_id,
            "visual_role": role,
            "critical": critical,
            "state": state,
            "planned_seconds": round(planned, 3),
            "placeholder": placeholder,
            "logical_repo_path": logical,
            "issues": sorted(set(issues)),
            "inspection": inspection,
        })

    planned_count = len(items)
    resolved = [x for x in items if x["state"] in {"resolved_clean", "resolved_degraded"}]
    missing = [x for x in items if x["state"] == "missing"]
    degraded = [x for x in items if x["state"] == "resolved_degraded"]
    technical = [x for x in items if x["state"] == "technical_failure"]
    unresolved_critical = [x for x in items if x["critical"] and x["state"] not in {"resolved_clean", "resolved_degraded"}]
    planned_seconds = sum(float(x["planned_seconds"]) for x in items)
    resolved_seconds = sum(float(x["planned_seconds"]) for x in resolved)
    cue_ratio = len(resolved) / planned_count if planned_count else 1.0
    sec_ratio = resolved_seconds / planned_seconds if planned_seconds else 1.0
    missing_noncritical = [x for x in missing if not x["critical"]]

    blockers: list[str] = []
    if cue_ratio < float(thresholds.get("min_resolved_cue_ratio", 0.8)):
        blockers.append("resolved_cue_ratio_below_threshold")
    if sec_ratio < float(thresholds.get("min_resolved_visual_seconds_ratio", 0.8)):
        blockers.append("resolved_visual_seconds_ratio_below_threshold")
    if len(missing_noncritical) > int(thresholds.get("max_missing_noncritical_cues", 3)):
        blockers.append("too_many_missing_noncritical_cues")
    if len(unresolved_critical) > int(thresholds.get("max_unresolved_critical_cues", 0)):
        blockers.append("critical_visual_unresolved")
    if len(technical) > int(thresholds.get("max_technical_failure_cues", 0)):
        blockers.append("technical_media_failure")
    if quality.get("low_resolution_blocks") and any("low_resolution" in x["issues"] for x in items):
        blockers.append("low_resolution_asset")
    if quality.get("short_video_blocks") and any("source_shorter_than_planned" in x["issues"] for x in items):
        blockers.append("short_video_asset")
    if quality.get("missing_license_label_blocks") and any("missing_license_label" in x["issues"] for x in items):
        blockers.append("missing_license_label")

    warnings = sorted({
        issue
        for item in items
        for issue in item["issues"]
        if issue not in {"unresolved_placeholder"}
    })
    actions: list[dict[str, Any]] = []
    for item in items:
        if item["state"] == "technical_failure":
            actions.append({
                "priority": "P0",
                "cue_id": item["cue_id"],
                "action": "replace_or_reencode_asset",
                "reason": "technical_media_failure",
            })
        elif item["state"] == "missing" and item["critical"]:
            actions.append({
                "priority": "P0",
                "cue_id": item["cue_id"],
                "action": "resolve_critical_visual",
                "reason": "critical_visual_unresolved",
            })
        elif item["state"] == "missing":
            actions.append({
                "priority": "P1",
                "cue_id": item["cue_id"],
                "action": "resolve_visual_or_accept_presenter",
                "reason": "noncritical_visual_unresolved",
            })
        elif "low_resolution" in item["issues"]:
            actions.append({
                "priority": "P2",
                "cue_id": item["cue_id"],
                "action": "prefer_higher_resolution_if_available",
                "reason": "low_resolution",
            })
        elif "source_shorter_than_planned" in item["issues"]:
            actions.append({
                "priority": "P2",
                "cue_id": item["cue_id"],
                "action": "find_longer_asset_or_adjust_hold",
                "reason": "source_shorter_than_planned",
            })
    actions.sort(key=lambda item: ({"P0": 0, "P1": 1, "P2": 2}.get(item["priority"], 9), item["cue_id"]))
    ready = not blockers
    return {
        "schema_version": SCHEMA_VERSION,
        "episode_date": episode_date,
        "status": "ready_to_record" if ready else "blocked_before_recording",
        "policy": policy,
        "summary": {
            "planned_cue_count": planned_count,
            "resolved_cue_count": len(resolved),
            "missing_cue_count": len(missing),
            "degraded_cue_count": len(degraded),
            "technical_failure_cue_count": len(technical),
            "unresolved_critical_cue_count": len(unresolved_critical),
            "planned_visual_seconds": round(planned_seconds, 3),
            "resolved_visual_seconds": round(resolved_seconds, 3),
            "resolved_cue_ratio": round(cue_ratio, 4),
            "resolved_visual_seconds_ratio": round(sec_ratio, 4),
        },
        "actions": actions,
        "gate": {
            "ready_to_record": ready,
            "promotion_blocking": str(policy.get("mode", "enforce")) == "enforce",
            "blockers": blockers,
            "warnings": warnings,
        },
        "items": items,
    }


def render_html(payload: dict[str, Any]) -> str:
    s = payload["summary"]
    rows = []
    for item in payload["items"]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(item['cue_id'])}</td>"
            f"<td>{html.escape(item['visual_role'])}</td>"
            f"<td>{'yes' if item['critical'] else 'no'}</td>"
            f"<td>{html.escape(item['state'])}</td>"
            f"<td>{item['planned_seconds']:.1f}s</td>"
            f"<td>{html.escape(', '.join(item['issues']))}</td>"
            "</tr>"
        )
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Asset readiness {html.escape(payload['episode_date'])}</title>
<style>body{{font-family:Arial,sans-serif;margin:28px;background:#111;color:#eee}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}}.card{{padding:16px;background:#1b1b1b;border:1px solid #333;border-radius:10px}}table{{width:100%;border-collapse:collapse;margin-top:22px}}th,td{{padding:8px;border-bottom:1px solid #333;text-align:left}}.bad{{color:#ff9b9b}}.good{{color:#a9e7a9}}</style></head><body>
<h1>Asset Readiness · {html.escape(payload['episode_date'])}</h1>
<h2 class="{'good' if payload['gate']['ready_to_record'] else 'bad'}">{html.escape(payload['status'])}</h2>
<div class="cards">
<div class="card"><strong>Cue coverage</strong><br>{s['resolved_cue_ratio']*100:.1f}%</div>
<div class="card"><strong>Seconds covered</strong><br>{s['resolved_visual_seconds_ratio']*100:.1f}%</div>
<div class="card"><strong>Missing cues</strong><br>{s['missing_cue_count']}</div>
<div class="card"><strong>Degraded</strong><br>{s['degraded_cue_count']}</div>
<div class="card"><strong>Critical unresolved</strong><br>{s['unresolved_critical_cue_count']}</div>
<div class="card"><strong>Technical failures</strong><br>{s['technical_failure_cue_count']}</div>
</div>
<p><strong>Blockers:</strong> {html.escape(', '.join(payload['gate']['blockers']) or 'none')}</p>
<h2>Recommended actions</h2>
<ul>{''.join(f"<li><strong>{html.escape(a['priority'])}</strong> · {html.escape(a['cue_id'])} · {html.escape(a['action'])}</li>" for a in payload.get('actions', [])) or '<li>none</li>'}</ul>
<table><thead><tr><th>Cue</th><th>Role</th><th>Critical</th><th>State</th><th>Planned</th><th>Issues</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
</body></html>"""


def write_asset_readiness(
    *,
    repo_root: Path,
    episode_dir: Path,
    policy_path: Path,
    enforce: bool,
) -> tuple[Path, Path, dict[str, Any]]:
    virtual = _read_json(episode_dir / "virtual_timeline.json")
    resolve = _read_json(episode_dir / "resolve_bridge_plan.json")
    preview_path = episode_dir / "pre_recording_preview_validation.json"
    preview = _read_json(preview_path) if preview_path.is_file() else None
    policy = _read_policy(policy_path)
    payload = build_asset_readiness(
        virtual_timeline=virtual,
        resolve_plan=resolve,
        preview_validation=preview,
        repo_root=repo_root,
        policy=policy,
    )
    validate_payload(payload, "asset_readiness.schema.json")
    json_path = episode_dir / "asset_readiness.json"
    html_path = episode_dir / "asset_readiness.html"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(render_html(payload), encoding="utf-8")
    if enforce and not payload["gate"]["ready_to_record"]:
        raise RuntimeError("Asset readiness gate blocked recording: " + ", ".join(payload["gate"]["blockers"]))
    return json_path, html_path, payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate pre-recording asset readiness")
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--scripts-dir", default="scripts")
    parser.add_argument("--policy", default="config/asset_readiness.yaml")
    parser.add_argument("--enforce", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.repo_root).resolve()
    episode = root / args.scripts_dir / args.target_date
    json_path, html_path, payload = write_asset_readiness(
        repo_root=root,
        episode_dir=episode,
        policy_path=root / args.policy,
        enforce=args.enforce,
    )
    print(json.dumps({
        "asset_readiness": str(json_path),
        "asset_readiness_html": str(html_path),
        "ready_to_record": payload["gate"]["ready_to_record"],
        "blockers": payload["gate"]["blockers"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
