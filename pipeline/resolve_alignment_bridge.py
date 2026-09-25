from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pipeline.resolve_bridge import (
    _ensure_bin,
    load_resolve_api,
)
from pipeline.schema_validation import validate_payload


SCHEMA_VERSION = 1


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _safe_recording_path(recordings_root: Path, relative: str) -> Path:
    path = (recordings_root / relative).resolve()
    try:
        path.relative_to(recordings_root.resolve())
    except ValueError as exc:
        raise ValueError(
            f"Recording path escapes recordings root: {relative}"
        ) from exc
    return path


def build_resolve_alignment_plan(
    *,
    recording_alignment: dict[str, Any],
) -> dict[str, Any]:
    episode_date = str(recording_alignment.get("episode_date", "") or "")
    if not episode_date:
        raise ValueError("recording_alignment.json requires episode_date")

    takes: list[dict[str, Any]] = []
    blockers: list[str] = []
    for item in recording_alignment.get("takes", []):
        if not isinstance(item, dict):
            continue
        take_id = str(item.get("take_id", "") or "")
        selected = (
            item.get("selected", {})
            if isinstance(item.get("selected"), dict)
            else {}
        )
        if not selected:
            blockers.append(f"missing_selected_retake:{take_id}")
            continue
        video = (
            selected.get("video", {})
            if isinstance(selected.get("video"), dict)
            else {}
        )
        external = (
            selected.get("external_audio", {})
            if isinstance(selected.get("external_audio"), dict)
            else {}
        )
        video_relative = str(video.get("relative_path", "") or "")
        if not video_relative:
            blockers.append(f"missing_selected_video:{take_id}")
            continue

        timebase = str(selected.get("timebase", "") or "video_source")
        trim = selected.get("trim", {}) if isinstance(selected.get("trim"), dict) else {}
        video_trim_ready = bool(selected.get("video_trim_ready"))
        external_relative = str(external.get("relative_path", "") or "")
        waveform_sync_required = bool(external_relative)

        takes.append(
            {
                "take_id": take_id,
                "retake_number": int(selected.get("retake_number", 0) or 0),
                "video_relative_path": video_relative,
                "external_audio_relative_path": external_relative or None,
                "audio_source": str(selected.get("audio_source", "") or ""),
                "waveform_sync_required": waveform_sync_required,
                "transcript_timebase": timebase,
                "video_trim_ready": video_trim_ready,
                "source_in_seconds": float(trim.get("source_in_seconds", 0) or 0),
                "source_out_seconds": float(trim.get("source_out_seconds", 0) or 0),
                "duration_seconds": float(trim.get("duration_seconds", 0) or 0),
            }
        )
        if timebase != "video_source":
            blockers.append(
                f"camera_scratch_audio_missing_for_automated_waveform_sync:{take_id}"
            )

    unique_blockers = sorted(set(blockers))
    return {
        "schema_version": SCHEMA_VERSION,
        "episode_date": episode_date,
        "status": "resolve_alignment_media_sync_plan",
        "project": {
            "name": f"AI News Daily · {episode_date}",
            "future_timeline_name": f"{episode_date} · Aligned Rough Cut",
        },
        "bins": {
            "video": "04_A-Roll_Recorded",
            "audio": "05_Audio_Recorded",
        },
        "audio_sync": {
            "mode": "waveform",
            "channel": "automatic",
            "retain_embedded_audio": True,
            "retain_video_metadata": True,
            "use_live_resolve_enum_constants": True,
            "verify_after_sync": True,
        },
        "resolve_native_transcription": {
            "enabled_by_default": False,
            "role": "diagnostic_only",
            "alignment_authority": False,
        },
        "readiness": {
            "plan_valid": True,
            "ready_for_media_sync": not unique_blockers,
            "ready_for_aligned_timeline_build": (
                not unique_blockers
                and bool(
                    recording_alignment.get("readiness", {}).get(
                        "ready_for_aligned_timeline"
                    )
                )
            ),
            "blockers": unique_blockers,
        },
        "summary": {
            "selected_take_count": len(takes),
            "waveform_sync_pair_count": sum(
                1 for item in takes if item["waveform_sync_required"]
            ),
            "embedded_only_take_count": sum(
                1 for item in takes if not item["waveform_sync_required"]
            ),
        },
        "takes": takes,
    }


def _sync_property_snapshot(media_pool_item: Any) -> dict[str, Any]:
    try:
        payload = media_pool_item.GetClipProperty()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        str(key): value
        for key, value in payload.items()
        if "sync" in str(key).lower() and "audio" in str(key).lower()
    }


def _sync_verified(
    *,
    before: dict[str, Any],
    after: dict[str, Any],
    direct_value: Any,
) -> bool:
    if after and after != before:
        return True
    for value in after.values():
        if value not in (None, "", "None", "0", 0, False):
            return True
    return False


def execute_resolve_media_sync(
    plan: dict[str, Any],
    *,
    recordings_root: Path,
    resolve: Any | None = None,
    reuse_project: bool = True,
) -> dict[str, Any]:
    blockers = [
        str(item)
        for item in plan.get("readiness", {}).get("blockers", [])
        if str(item)
    ]
    if blockers:
        raise RuntimeError(
            "Resolve alignment media sync is blocked: " + ", ".join(blockers)
        )

    if resolve is None:
        module = load_resolve_api()
        resolve = module.scriptapp("Resolve")
    if not resolve:
        raise RuntimeError("Could not connect to DaVinci Resolve scripting API")

    manager = resolve.GetProjectManager()
    if not manager:
        raise RuntimeError("Resolve ProjectManager is unavailable")
    project_name = str(plan.get("project", {}).get("name", "") or "")
    projects = manager.GetProjectListInCurrentFolder() or []
    if project_name in projects:
        if not reuse_project:
            raise RuntimeError(
                f"Resolve project {project_name!r} already exists"
            )
        project = manager.LoadProject(project_name)
    else:
        project = manager.CreateProject(project_name)
    if not project:
        raise RuntimeError(f"Could not create/load Resolve project {project_name!r}")

    media_pool = project.GetMediaPool()
    if not media_pool:
        raise RuntimeError("Resolve MediaPool is unavailable")
    root = media_pool.GetRootFolder()
    video_bin = _ensure_bin(
        media_pool,
        root,
        str(plan.get("bins", {}).get("video", "04_A-Roll_Recorded")),
    )
    audio_bin = _ensure_bin(
        media_pool,
        root,
        str(plan.get("bins", {}).get("audio", "05_Audio_Recorded")),
    )

    imported: dict[str, Any] = {}
    sync_results: list[dict[str, Any]] = []
    for take in plan.get("takes", []):
        if not isinstance(take, dict):
            continue
        take_id = str(take.get("take_id", "") or "")
        video_relative = str(take.get("video_relative_path", "") or "")
        video_path = _safe_recording_path(recordings_root, video_relative)
        if not video_path.is_file():
            raise FileNotFoundError(f"Recorded video missing: {video_relative}")

        if media_pool.SetCurrentFolder(video_bin) is False:
            raise RuntimeError("Resolve could not select recorded A-roll bin")
        video_items = media_pool.ImportMedia([str(video_path)])
        if not video_items:
            raise RuntimeError(f"Resolve failed to import {video_relative}")
        video_item = video_items[0]
        imported[video_relative] = video_item

        audio_relative = str(
            take.get("external_audio_relative_path", "") or ""
        )
        if not audio_relative:
            sync_results.append(
                {
                    "take_id": take_id,
                    "retake_number": int(take.get("retake_number", 0) or 0),
                    "waveform_sync_required": False,
                    "verified": True,
                    "verification": "embedded_audio_only",
                }
            )
            continue

        audio_path = _safe_recording_path(recordings_root, audio_relative)
        if not audio_path.is_file():
            raise FileNotFoundError(f"External audio missing: {audio_relative}")
        if media_pool.SetCurrentFolder(audio_bin) is False:
            raise RuntimeError("Resolve could not select recorded audio bin")
        audio_items = media_pool.ImportMedia([str(audio_path)])
        if not audio_items:
            raise RuntimeError(f"Resolve failed to import {audio_relative}")
        audio_item = audio_items[0]
        imported[audio_relative] = audio_item

        required_attrs = (
            "AUDIO_SYNC_MODE",
            "AUDIO_SYNC_WAVEFORM",
            "AUDIO_SYNC_CHANNEL_NUMBER",
            "AUDIO_SYNC_CHANNEL_AUTOMATIC",
            "AUDIO_SYNC_RETAIN_EMBEDDED_AUDIO",
            "AUDIO_SYNC_RETAIN_VIDEO_METADATA",
        )
        missing_attrs = [
            name for name in required_attrs if not hasattr(resolve, name)
        ]
        if missing_attrs:
            raise RuntimeError(
                "Resolve lacks required live audio-sync enums: "
                + ", ".join(missing_attrs)
            )

        settings = {
            getattr(resolve, "AUDIO_SYNC_MODE"): getattr(
                resolve, "AUDIO_SYNC_WAVEFORM"
            ),
            getattr(resolve, "AUDIO_SYNC_CHANNEL_NUMBER"): getattr(
                resolve, "AUDIO_SYNC_CHANNEL_AUTOMATIC"
            ),
            getattr(resolve, "AUDIO_SYNC_RETAIN_EMBEDDED_AUDIO"): bool(
                plan.get("audio_sync", {}).get(
                    "retain_embedded_audio", True
                )
            ),
            getattr(resolve, "AUDIO_SYNC_RETAIN_VIDEO_METADATA"): bool(
                plan.get("audio_sync", {}).get(
                    "retain_video_metadata", True
                )
            ),
        }
        before = _sync_property_snapshot(video_item)
        direct_result = media_pool.AutoSyncAudio(
            [video_item, audio_item],
            settings,
        )
        after = _sync_property_snapshot(video_item)
        verified = _sync_verified(
            before=before,
            after=after,
            direct_value=direct_result,
        )
        sync_results.append(
            {
                "take_id": take_id,
                "retake_number": int(take.get("retake_number", 0) or 0),
                "waveform_sync_required": True,
                "api_return": bool(direct_result),
                "verified": verified,
                "verification": (
                    "clip_property_readback"
                    if verified
                    else "unverified_sync_result"
                ),
                "sync_properties_before": before,
                "sync_properties_after": after,
            }
        )
        if not verified:
            raise RuntimeError(
                f"Resolve waveform sync could not be verified for {take_id}"
            )

    if manager.SaveProject() is False:
        raise RuntimeError("Resolve failed to save project after media sync")

    return {
        "schema_version": SCHEMA_VERSION,
        "episode_date": plan.get("episode_date"),
        "status": "resolve_alignment_media_synced",
        "project_name": project_name,
        "imported_media_count": len(imported),
        "sync_pair_count": sum(
            1 for item in sync_results if item["waveform_sync_required"]
        ),
        "verified_sync_pair_count": sum(
            1
            for item in sync_results
            if item["waveform_sync_required"] and item["verified"]
        ),
        "all_required_syncs_verified": all(
            item["verified"] for item in sync_results
        ),
        "timeline_created": False,
        "next_step": "build_aligned_timeline_then_import_as_new_resolve_timeline",
        "sync_results": sync_results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare or execute Resolve waveform sync for selected A-roll"
    )
    parser.add_argument("--alignment", required=True)
    parser.add_argument("--recordings-root", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--no-reuse-project", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    alignment_path = Path(args.alignment).resolve()
    plan = build_resolve_alignment_plan(
        recording_alignment=_read_json(alignment_path)
    )
    output_path = (
        Path(args.output).resolve()
        if args.output
        else alignment_path.with_name("resolve_alignment_plan.json")
    )
    validate_payload(plan, "resolve_alignment_plan.schema.json")
    output_path.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    payload: dict[str, Any] = {
        "resolve_alignment_plan": str(output_path),
        "executed": False,
    }
    if args.execute:
        if not args.recordings_root:
            raise RuntimeError("--recordings-root is required with --execute")
        execution = execute_resolve_media_sync(
            plan,
            recordings_root=Path(args.recordings_root).resolve(),
            reuse_project=not args.no_reuse_project,
        )
        execution_path = output_path.with_name(
            "resolve_alignment_execution.json"
        )
        execution_path.write_text(
            json.dumps(execution, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        payload.update(
            {
                "executed": True,
                "resolve_alignment_execution": str(execution_path),
                "all_required_syncs_verified": execution[
                    "all_required_syncs_verified"
                ],
            }
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
