from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml


STYLE_SCHEMA_VERSION = 1
KNOWN_VISUAL_ROLES = {
    "evidence",
    "explanation",
    "context",
    "historical_mirror",
    "analogy",
    "contrast",
    "emotional_grounding",
    "rhythm",
}


def load_editing_style(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing editing style: {path}")
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError("editing_style.yaml must contain a mapping")
    validate_editing_style(data)
    payload = dict(data)
    parts = list(path.parts)
    if "config" in parts:
        config_index = len(parts) - 1 - parts[::-1].index("config")
        source_path = Path(*parts[config_index:]).as_posix()
    else:
        source_path = path.name
    payload["_source_path"] = source_path
    payload["_sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return payload


def validate_editing_style(style: dict[str, Any]) -> None:
    if int(style.get("schema_version", 0) or 0) != STYLE_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported editing style schema_version={style.get('schema_version')}"
        )
    if not str(style.get("style_id", "") or "").strip():
        raise ValueError("editing_style.yaml requires style_id")

    transitions = style.get("transitions", {})
    if not isinstance(transitions, dict):
        raise ValueError("editing_style.transitions must be a mapping")
    allowed = transitions.get("allowed", [])
    if not isinstance(allowed, list) or "hard_cut" not in allowed:
        raise ValueError("editing_style.transitions.allowed must include hard_cut")
    default_transition = str(transitions.get("default", "") or "")
    if default_transition not in allowed:
        raise ValueError("editing_style.transitions.default must be in allowed")

    presenter = style.get("presenter", {})
    target_share = presenter.get("target_visual_share", {}) if isinstance(presenter, dict) else {}
    min_share = float(target_share.get("min", 0) or 0)
    max_share = float(target_share.get("max", 0) or 0)
    if not (0 <= min_share <= max_share <= 1):
        raise ValueError("presenter.target_visual_share must satisfy 0 <= min <= max <= 1")

    roles = style.get("visual_roles", {})
    if not isinstance(roles, dict):
        raise ValueError("editing_style.visual_roles must be a mapping")
    missing = KNOWN_VISUAL_ROLES - set(roles)
    if missing:
        raise ValueError(f"editing_style.visual_roles missing: {sorted(missing)}")
    for role, rule in roles.items():
        if role not in KNOWN_VISUAL_ROLES:
            raise ValueError(f"Unknown visual role in editing_style.yaml: {role}")
        if not isinstance(rule, dict):
            raise ValueError(f"visual_roles.{role} must be a mapping")
        duration = rule.get("duration_seconds", {})
        try:
            minimum = float(duration["min"])
            preferred = float(duration["preferred"])
            maximum = float(duration["max"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"visual_roles.{role}.duration_seconds is invalid") from exc
        if not (0 < minimum <= preferred <= maximum):
            raise ValueError(
                f"visual_roles.{role}.duration_seconds must satisfy 0 < min <= preferred <= max"
            )


def public_style_metadata(style: dict[str, Any]) -> dict[str, Any]:
    return {
        "applied": True,
        "schema_version": int(style.get("schema_version", STYLE_SCHEMA_VERSION)),
        "style_id": str(style.get("style_id", "") or ""),
        "name": str(style.get("name", "") or ""),
        "authority": str(style.get("authority", "") or ""),
        "source_path": str(style.get("_source_path", "") or ""),
        "sha256": str(style.get("_sha256", "") or ""),
    }


def visual_role_rule(style: dict[str, Any] | None, role: str) -> dict[str, Any]:
    if not style:
        return {}
    roles = style.get("visual_roles", {})
    value = roles.get(role, {}) if isinstance(roles, dict) else {}
    return value if isinstance(value, dict) else {}


def media_defaults(
    style: dict[str, Any] | None,
    *,
    role: str,
    asset_type: str,
) -> dict[str, str]:
    if not style:
        return {}
    rule = visual_role_rule(style, role)
    transitions = style.get("transitions", {}) if isinstance(style.get("transitions"), dict) else {}
    media = style.get("media", {}) if isinstance(style.get("media"), dict) else {}
    transition = str(rule.get("default_transition", "") or transitions.get("default", "hard_cut"))
    if asset_type == "video":
        treatment = str(rule.get("video_treatment", "") or media.get("video_default_treatment", "natural_motion"))
    else:
        treatment = str(rule.get("image_treatment", "") or media.get("image_default_treatment", "subtle_push_in"))
    return {"transition": transition, "treatment": treatment}


def lint_timeline(
    timeline: list[dict[str, Any]],
    style: dict[str, Any],
    *,
    duration_seconds: float,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    allowed_transitions = set(style.get("transitions", {}).get("allowed", []))
    roles = style.get("visual_roles", {})
    opening = style.get("opening", {})
    media_cfg = style.get("media", {})
    presenter_cfg = style.get("presenter", {})

    total_presenter = sum(
        float(item.get("duration_seconds", 0) or 0)
        for item in timeline
        if item.get("mode") == "presenter"
    )
    share = total_presenter / max(float(duration_seconds), 0.001)
    target = presenter_cfg.get("target_visual_share", {})
    min_share = float(target.get("min", 0) or 0)
    max_share = float(target.get("max", 1) or 1)
    if share < min_share:
        warnings.append({
            "code": "presenter_share_low",
            "severity": "warning",
            "message": f"Presenter visual share {share:.1%} is below style target {min_share:.1%}.",
        })
    elif share > max_share:
        warnings.append({
            "code": "presenter_share_high",
            "severity": "info",
            "message": f"Presenter visual share {share:.1%} is above style target {max_share:.1%}; verify that long camera runs remain intentional.",
        })

    first_presenter = next(
        (float(item.get("start_seconds", 0) or 0) for item in timeline if item.get("mode") == "presenter"),
        None,
    )
    deadline = float(opening.get("presenter_anchor_deadline_seconds", 0) or 0)
    if first_presenter is None or first_presenter > deadline:
        warnings.append({
            "code": "opening_presenter_anchor_late",
            "severity": "warning",
            "message": f"First presenter appearance starts at {first_presenter if first_presenter is not None else 'never'}s; style target is <= {deadline:.1f}s.",
        })

    max_media_run = float(media_cfg.get("maximum_continuous_media_seconds", 0) or 0)
    opening_max_media_run = float(opening.get("maximum_continuous_media_seconds", max_media_run) or max_media_run)
    max_presenter_run = float(presenter_cfg.get("maximum_uninterrupted_seconds", 0) or 0)

    current_mode = None
    run_start = 0.0
    run_end = 0.0
    run_ids: list[str] = []

    def finish_run(mode: str | None, start: float, end: float, ids: list[str]) -> None:
        if not mode:
            return
        length = max(0.0, end - start)
        if mode == "media":
            limit = opening_max_media_run if start < float(opening.get("dense_visual_window_seconds", 0) or 0) else max_media_run
            if limit > 0 and length > limit:
                warnings.append({
                    "code": "continuous_media_too_long",
                    "severity": "warning",
                    "message": f"Continuous media run {length:.1f}s exceeds {limit:.1f}s style limit.",
                    "segment_ids": list(ids),
                })
        elif mode == "presenter" and max_presenter_run > 0 and length > max_presenter_run:
            warnings.append({
                "code": "presenter_run_too_long",
                "severity": "info",
                "message": f"Uninterrupted presenter run {length:.1f}s exceeds {max_presenter_run:.1f}s attention-reset target.",
                "segment_ids": list(ids),
            })

    for item in timeline:
        mode = str(item.get("mode", "") or "")
        start = float(item.get("start_seconds", 0) or 0)
        end = float(item.get("end_seconds", start) or start)
        segment_id = str(item.get("segment_id", "") or "")
        if mode != current_mode:
            finish_run(current_mode, run_start, run_end, run_ids)
            current_mode = mode
            run_start = start
            run_end = end
            run_ids = [segment_id]
        else:
            run_end = end
            run_ids.append(segment_id)

        director = item.get("director", {}) if isinstance(item.get("director"), dict) else {}
        for key in ("transition_in", "transition_out"):
            transition = str(director.get(key, "") or "")
            if transition and transition not in allowed_transitions:
                warnings.append({
                    "code": "invalid_transition",
                    "severity": "error",
                    "message": f"{segment_id} uses transition {transition!r}, outside editing style allow-list.",
                    "segment_ids": [segment_id],
                })

        if mode != "media":
            continue
        role = str(director.get("visual_role", "") or "")
        if role not in roles:
            warnings.append({
                "code": "unknown_visual_role",
                "severity": "error",
                "message": f"{segment_id} uses unknown visual_role={role!r}.",
                "segment_ids": [segment_id],
            })
            continue
        duration_rule = roles[role].get("duration_seconds", {})
        minimum = float(duration_rule.get("min", 0) or 0)
        maximum = float(duration_rule.get("max", 0) or 0)
        length = max(0.0, end - start)
        if minimum and length < minimum - 0.05:
            warnings.append({
                "code": "media_segment_short",
                "severity": "info",
                "message": f"{segment_id} ({role}) is {length:.1f}s, below preferred style floor {minimum:.1f}s.",
                "segment_ids": [segment_id],
            })
        if maximum and length > maximum + 0.05:
            warnings.append({
                "code": "media_segment_long",
                "severity": "warning",
                "message": f"{segment_id} ({role}) is {length:.1f}s, above style ceiling {maximum:.1f}s.",
                "segment_ids": [segment_id],
            })

    finish_run(current_mode, run_start, run_end, run_ids)

    rare = {"none", "hard_cut"}
    visible_count = sum(
        1
        for item in timeline
        if str((item.get("director") or {}).get("transition_in", "") or "") not in rare
    )
    per_minute = visible_count / max(float(duration_seconds) / 60.0, 0.01)
    maximum_visible = float(style.get("transitions", {}).get("maximum_visible_transitions_per_minute", 0) or 0)
    if maximum_visible and per_minute > maximum_visible:
        warnings.append({
            "code": "visible_transition_density_high",
            "severity": "warning",
            "message": f"Visible transition density {per_minute:.2f}/min exceeds style maximum {maximum_visible:.2f}/min.",
        })

    return warnings
