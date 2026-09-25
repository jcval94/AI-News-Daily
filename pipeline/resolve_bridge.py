from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _frames(seconds: float, fps: int) -> int:
    return max(0, int(round(float(seconds) * int(fps))))


def _parse_resolution(value: str) -> tuple[int, int]:
    raw = str(value or "").lower().replace(" ", "")
    if "x" not in raw:
        raise ValueError(f"Invalid resolution: {value!r}")
    left, right = raw.split("x", 1)
    width, height = int(left), int(right)
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid resolution: {value!r}")
    return width, height


def _placeholder_index(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in manifest.get("items", []) if isinstance(manifest, dict) else []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("placeholder_id", "") or "").strip()
        if not key:
            continue
        if key in result:
            raise ValueError(f"Duplicate placeholder_id={key}")
        result[key] = item
    return result


def _source_path(
    *,
    clip: dict[str, Any],
    placeholder_index: dict[str, dict[str, Any]],
) -> tuple[str, str, bool]:
    track_id = str(clip.get("_track_id", "") or "")
    source = clip.get("source", {}) if isinstance(clip.get("source"), dict) else {}
    if track_id == "V1":
        replace_key = str(clip.get("replace_key", "") or clip.get("take_id", "") or "")
        item = placeholder_index.get(f"take:{replace_key}")
        if not item:
            return "", "01_A-Roll_Placeholders", True
        return str(item.get("logical_repo_path", "") or ""), "01_A-Roll_Placeholders", True

    if track_id == "V2" and clip.get("status") == "placeholder":
        cue_id = str(clip.get("cue_id", "") or "")
        item = placeholder_index.get(f"cue:{cue_id}")
        if not item:
            return "", "99_Missing_B-Roll", True
        return str(item.get("logical_repo_path", "") or ""), "99_Missing_B-Roll", True

    if track_id == "V2":
        logical = str(source.get("logical_media_path", "") or source.get("media_file", "") or "")
        return logical.replace("\\", "/"), "02_B-Roll", False

    return "", "03_Graphics", False


def build_resolve_plan(
    *,
    virtual_timeline: dict[str, Any],
    placeholder_manifest: dict[str, Any],
    repo_root: Path,
    project_name: str | None = None,
    timeline_name: str | None = None,
) -> dict[str, Any]:
    episode_date = str(virtual_timeline.get("episode_date", "") or "").strip()
    if not episode_date:
        raise ValueError("virtual_timeline.json requires episode_date")
    fmt = virtual_timeline.get("format", {}) if isinstance(virtual_timeline.get("format"), dict) else {}
    fps = int(fmt.get("frame_rate_fps", 0) or 0)
    if fps <= 0:
        raise ValueError("Resolve Bridge requires positive frame_rate_fps")
    width, height = _parse_resolution(str(fmt.get("resolution", "") or ""))
    duration_seconds = float((virtual_timeline.get("timing", {}) or {}).get("duration_seconds", 0) or 0)
    if duration_seconds <= 0:
        raise ValueError("Resolve Bridge requires positive timeline duration")

    placeholders = _placeholder_index(placeholder_manifest)
    imports: dict[str, dict[str, Any]] = {}
    placements: list[dict[str, Any]] = []
    blockers: list[str] = []

    video_track_map = {"V1": 1, "V2": 2, "V3": 3, "V4": 4}
    for track in virtual_timeline.get("tracks", []):
        if not isinstance(track, dict):
            continue
        track_id = str(track.get("track_id", "") or "")
        if track_id not in video_track_map:
            continue
        for raw_clip in track.get("clips", []):
            if not isinstance(raw_clip, dict):
                continue
            clip = dict(raw_clip)
            clip["_track_id"] = track_id
            logical_path, bin_name, is_placeholder = _source_path(
                clip=clip,
                placeholder_index=placeholders,
            )
            if not logical_path:
                blocker = f"missing_source_mapping:{clip.get('clip_id')}"
                blockers.append(blocker)
                continue
            physical = (repo_root / logical_path).resolve()
            repo_resolved = repo_root.resolve()
            try:
                physical.relative_to(repo_resolved)
            except ValueError as exc:
                raise ValueError(f"Resolve media path escapes repo root: {logical_path}") from exc
            exists = physical.is_file()
            if not exists:
                blockers.append(f"missing_file:{logical_path}")

            imports.setdefault(
                logical_path,
                {
                    "logical_repo_path": logical_path,
                    "absolute_path": str(physical),
                    "bin": bin_name,
                    "exists": exists,
                    "placeholder": is_placeholder,
                },
            )
            start_seconds = float(clip.get("timeline_start_seconds", 0) or 0)
            duration = float(clip.get("duration_seconds", 0) or 0)
            if duration <= 0:
                raise ValueError(f"Resolve placement has non-positive duration: {clip.get('clip_id')}")
            placements.append({
                "placement_id": str(clip.get("clip_id", "") or ""),
                "track_id": track_id,
                "track_index": video_track_map[track_id],
                "kind": str(clip.get("kind", "") or ""),
                "take_id": clip.get("take_id"),
                "cue_id": clip.get("cue_id"),
                "replace_key": clip.get("replace_key"),
                "logical_repo_path": logical_path,
                "record_frame": _frames(start_seconds, fps),
                "duration_frames": max(1, _frames(duration, fps)),
                "timeline_start_seconds": start_seconds,
                "duration_seconds": duration,
                "placeholder": is_placeholder,
            })

    placements.sort(key=lambda item: (int(item["track_index"]), int(item["record_frame"])))
    for track_index in sorted({int(item["track_index"]) for item in placements}):
        previous_end = 0
        for item in [x for x in placements if int(x["track_index"]) == track_index]:
            start = int(item["record_frame"])
            end = start + int(item["duration_frames"])
            if start < previous_end:
                raise ValueError(
                    f"Resolve plan overlap on video track {track_index}: {item['placement_id']}"
                )
            previous_end = end

    markers = []
    for marker in virtual_timeline.get("markers", []):
        if not isinstance(marker, dict):
            continue
        kind = str(marker.get("kind", "") or "")
        seconds = float(marker.get("timeline_seconds", 0) or 0)
        markers.append({
            "marker_id": str(marker.get("marker_id", "") or ""),
            "kind": kind,
            "name": str(marker.get("label", "") or marker.get("marker_id", "") or ""),
            "note": str(marker.get("take_id", "") or marker.get("section_key", "") or ""),
            "frame": _frames(seconds, fps),
            "color": "Blue" if kind == "section" else "Cyan",
            "duration_frames": 1,
        })

    unique_blockers = sorted(set(blockers))
    return {
        "schema_version": SCHEMA_VERSION,
        "episode_date": episode_date,
        "status": "resolve_bridge_v0_plan",
        "project": {
            "name": project_name or f"AI News Daily · {episode_date}",
            "timeline_name": timeline_name or f"{episode_date} · Rough Cut",
            "settings": {
                "timelineResolutionWidth": str(width),
                "timelineResolutionHeight": str(height),
                "timelineFrameRate": str(fps),
                "timelinePlaybackFrameRate": str(fps),
            },
        },
        "bins": [
            "01_A-Roll_Placeholders",
            "02_B-Roll",
            "03_Graphics",
            "99_Missing_B-Roll",
        ],
        "tracks": {
            "video": [
                {"index": 1, "name": "V1 · JC A-Roll"},
                {"index": 2, "name": "V2 · B-Roll / Evidence"},
                {"index": 3, "name": "V3 · Graphics"},
                {"index": 4, "name": "V4 · Titles"},
            ],
            "audio": [{"index": 1, "name": "A1 · JC Dialogue"}],
        },
        "imports": list(imports.values()),
        "placements": placements,
        "markers": markers,
        "readiness": {
            "plan_valid": True,
            "ready_for_resolve_execution": not unique_blockers,
            "final_edit_ready": False,
            "blockers": unique_blockers + ["real_a_roll_not_ingested"],
        },
        "summary": {
            "import_count": len(imports),
            "placement_count": len(placements),
            "presenter_placeholder_count": sum(
                1 for item in placements if item["track_id"] == "V1" and item["placeholder"]
            ),
            "broll_count": sum(1 for item in placements if item["track_id"] == "V2"),
            "broll_placeholder_count": sum(
                1 for item in placements if item["track_id"] == "V2" and item["placeholder"]
            ),
            "marker_count": len(markers),
            "duration_seconds": duration_seconds,
            "frame_rate_fps": fps,
        },
    }


def _resolve_module_candidates() -> list[Path]:
    candidates: list[Path] = []
    env_root = os.getenv("RESOLVE_SCRIPT_API", "").strip()
    if env_root:
        candidates.append(Path(env_root) / "Modules")
        candidates.append(Path(env_root))
    program_data = os.getenv("PROGRAMDATA", "").strip()
    if program_data:
        candidates.append(
            Path(program_data)
            / "Blackmagic Design"
            / "DaVinci Resolve"
            / "Support"
            / "Developer"
            / "Scripting"
            / "Modules"
        )
    candidates.extend([
        Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"),
        Path("/opt/resolve/Developer/Scripting/Modules"),
    ])
    return candidates


def load_resolve_api() -> Any:
    try:
        return importlib.import_module("DaVinciResolveScript")
    except ImportError:
        pass
    for path in _resolve_module_candidates():
        if path.is_dir() and str(path) not in sys.path:
            sys.path.append(str(path))
            try:
                return importlib.import_module("DaVinciResolveScript")
            except ImportError:
                continue
    raise RuntimeError(
        "DaVinciResolveScript is not importable. Run inside Resolve or configure "
        "RESOLVE_SCRIPT_API / the Developer Scripting Modules path."
    )


def _folder_by_name(parent: Any, name: str) -> Any | None:
    for child in parent.GetSubFolderList() or []:
        if child and child.GetName() == name:
            return child
    return None


def _ensure_bin(media_pool: Any, root: Any, name: str) -> Any:
    existing = _folder_by_name(root, name)
    if existing:
        return existing
    created = media_pool.AddSubFolder(root, name)
    if not created:
        raise RuntimeError(f"Resolve could not create Media Pool bin {name!r}")
    return created


def _timeline_exists(project: Any, name: str) -> bool:
    count = int(project.GetTimelineCount() or 0)
    for index in range(1, count + 1):
        timeline = project.GetTimelineByIndex(index)
        if timeline and timeline.GetName() == name:
            return True
    return False


def execute_resolve_plan(
    plan: dict[str, Any],
    *,
    repo_root: Path,
    resolve: Any | None = None,
    reuse_project: bool = False,
) -> dict[str, Any]:
    readiness = plan.get("readiness", {}) if isinstance(plan.get("readiness"), dict) else {}
    blockers = [
        str(item)
        for item in readiness.get("blockers", [])
        if str(item).startswith(("missing_file:", "missing_source_mapping:"))
    ]
    if blockers:
        raise RuntimeError("Resolve execution blocked by missing media: " + ", ".join(blockers))

    if resolve is None:
        module = load_resolve_api()
        resolve = module.scriptapp("Resolve")
    if not resolve:
        raise RuntimeError("Could not connect to DaVinci Resolve scripting API")

    manager = resolve.GetProjectManager()
    if not manager:
        raise RuntimeError("Resolve ProjectManager is unavailable")
    project_name = str(plan["project"]["name"])
    project = None
    project_list = manager.GetProjectListInCurrentFolder() or []
    if project_name in project_list:
        if not reuse_project:
            raise RuntimeError(
                f"Resolve project {project_name!r} already exists; use --reuse-project or another name"
            )
        project = manager.LoadProject(project_name)
    else:
        project = manager.CreateProject(project_name)
    if not project:
        raise RuntimeError(f"Resolve could not create/load project {project_name!r}")

    for key, value in plan["project"]["settings"].items():
        if project.SetSetting(str(key), str(value)) is False:
            raise RuntimeError(f"Resolve rejected project setting {key}={value}")

    media_pool = project.GetMediaPool()
    if not media_pool:
        raise RuntimeError("Resolve MediaPool is unavailable")
    root = media_pool.GetRootFolder()
    bins = {name: _ensure_bin(media_pool, root, name) for name in plan.get("bins", [])}

    imported: dict[str, Any] = {}
    for item in plan.get("imports", []):
        logical = str(item.get("logical_repo_path", "") or "")
        path = (repo_root / logical).resolve()
        if not path.is_file():
            raise RuntimeError(f"Resolve import file missing: {logical}")
        bin_name = str(item.get("bin", "") or "")
        folder = bins.get(bin_name)
        if not folder:
            raise RuntimeError(f"Resolve bin missing from plan: {bin_name}")
        if media_pool.SetCurrentFolder(folder) is False:
            raise RuntimeError(f"Resolve could not select bin {bin_name!r}")
        results = media_pool.ImportMedia([str(path)]) or []
        if len(results) != 1:
            raise RuntimeError(f"Resolve failed to import {logical}")
        imported[logical] = results[0]

    timeline_name = str(plan["project"]["timeline_name"])
    if _timeline_exists(project, timeline_name):
        raise RuntimeError(
            f"Resolve timeline {timeline_name!r} already exists; v0 refuses destructive overwrite"
        )
    timeline = media_pool.CreateEmptyTimeline(timeline_name)
    if not timeline:
        raise RuntimeError(f"Resolve could not create timeline {timeline_name!r}")
    project.SetCurrentTimeline(timeline)

    while int(timeline.GetTrackCount("video") or 0) < 4:
        if timeline.AddTrack("video") is False:
            raise RuntimeError("Resolve could not add required video track")
    while int(timeline.GetTrackCount("audio") or 0) < 1:
        if timeline.AddTrack("audio") is False:
            raise RuntimeError("Resolve could not add required audio track")

    for spec in plan.get("tracks", {}).get("video", []):
        timeline.SetTrackName("video", int(spec["index"]), str(spec["name"]))
    for spec in plan.get("tracks", {}).get("audio", []):
        timeline.SetTrackName("audio", int(spec["index"]), str(spec["name"]))

    appended = 0
    for item in plan.get("placements", []):
        logical = str(item["logical_repo_path"])
        media_item = imported.get(logical)
        if not media_item:
            raise RuntimeError(f"Resolve placement references unimported media: {logical}")
        duration = int(item["duration_frames"])
        clip_info = {
            "mediaPoolItem": media_item,
            "startFrame": 0,
            "endFrame": max(0, duration - 1),
            "recordFrame": int(item["record_frame"]),
            "trackIndex": int(item["track_index"]),
            "mediaType": 1,
        }
        result = media_pool.AppendToTimeline([clip_info])
        if not result:
            raise RuntimeError(f"Resolve could not append placement {item['placement_id']}")
        appended += 1

    markers_added = 0
    for marker in plan.get("markers", []):
        ok = timeline.AddMarker(
            int(marker["frame"]),
            str(marker["color"]),
            str(marker["name"]),
            str(marker.get("note", "") or ""),
            int(marker.get("duration_frames", 1) or 1),
            str(marker.get("marker_id", "") or ""),
        )
        if ok is False:
            raise RuntimeError(f"Resolve could not add marker {marker['marker_id']}")
        markers_added += 1

    if manager.SaveProject() is False:
        raise RuntimeError("Resolve failed to save project")

    return {
        "schema_version": 1,
        "status": "resolve_bridge_v0_executed",
        "project_name": project_name,
        "timeline_name": timeline_name,
        "imported_media_count": len(imported),
        "appended_placement_count": appended,
        "marker_count": markers_added,
        "real_a_roll_ingested": False,
        "final_edit_ready": False,
    }


def write_resolve_plan(
    *,
    repo_root: Path,
    episode_dir: Path,
    project_name: str | None = None,
    timeline_name: str | None = None,
) -> Path:
    virtual_path = episode_dir / "virtual_timeline.json"
    placeholder_path = episode_dir / "placeholder_media" / "placeholder_manifest.json"
    if not virtual_path.is_file():
        raise FileNotFoundError(f"Missing virtual timeline: {virtual_path}")
    if not placeholder_path.is_file():
        raise FileNotFoundError(f"Missing placeholder manifest: {placeholder_path}")
    plan = build_resolve_plan(
        virtual_timeline=_read_json(virtual_path),
        placeholder_manifest=_read_json(placeholder_path),
        repo_root=repo_root,
        project_name=project_name,
        timeline_name=timeline_name,
    )
    destination = episode_dir / "resolve_bridge_plan.json"
    destination.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan or execute the DaVinci Resolve v0 bridge")
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--scripts-dir", default="scripts")
    parser.add_argument("--project-name", default="")
    parser.add_argument("--timeline-name", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--reuse-project", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    episode_dir = repo_root / args.scripts_dir / args.target_date
    plan_path = write_resolve_plan(
        repo_root=repo_root,
        episode_dir=episode_dir,
        project_name=args.project_name or None,
        timeline_name=args.timeline_name or None,
    )
    result: dict[str, Any] = {"resolve_bridge_plan": str(plan_path), "executed": False}
    if args.execute:
        execution = execute_resolve_plan(
            _read_json(plan_path),
            repo_root=repo_root,
            reuse_project=args.reuse_project,
        )
        execution_path = episode_dir / "resolve_bridge_execution.json"
        execution_path.write_text(
            json.dumps(execution, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        result.update({"executed": True, "execution": str(execution_path)})
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
