from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import opentimelineio as otio


def build_smoke_otio(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    timeline = otio.schema.Timeline(name="AI News OTIO Smoke")
    track = otio.schema.Track(name="V1 Smoke", kind=otio.schema.TrackKind.Video)
    track.append(
        otio.schema.Gap(
            source_range=otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(0, 30),
                duration=otio.opentime.RationalTime(30, 30),
            )
        )
    )
    timeline.tracks.append(track)
    otio.adapters.write_to_file(timeline, str(path))
    readback = otio.adapters.read_from_file(str(path))
    if readback.name != "AI News OTIO Smoke" or len(readback.tracks) != 1:
        raise RuntimeError("OTIO core smoke round-trip failed")
    return path


def run_resolve_otio_smoke(
    resolve: Any,
    *,
    work_root: Path,
    project_name: str = "__AI_NEWS_LOCAL_ACCEPTANCE__",
) -> dict[str, Any]:
    manager = resolve.GetProjectManager()
    if not manager:
        raise RuntimeError("Resolve ProjectManager is unavailable")
    projects = manager.GetProjectListInCurrentFolder() or []
    project = manager.LoadProject(project_name) if project_name in projects else manager.CreateProject(project_name)
    if not project:
        raise RuntimeError("Resolve could not create/load the local acceptance project")
    media_pool = project.GetMediaPool()
    if not media_pool or not hasattr(media_pool, "ImportTimelineFromFile"):
        raise RuntimeError("Resolve MediaPool does not expose ImportTimelineFromFile")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    timeline_name = f"AI News OTIO Smoke {stamp}"
    smoke_path = build_smoke_otio(work_root / "acceptance" / f"{stamp}.otio")
    timeline = media_pool.ImportTimelineFromFile(
        str(smoke_path),
        {"timelineName": timeline_name, "importSourceClips": False},
    )
    if not timeline or str(timeline.GetName()) != timeline_name:
        raise RuntimeError("Resolve rejected or renamed the native OTIO smoke timeline")
    if manager.SaveProject() is False:
        raise RuntimeError("Resolve could not save the acceptance project")
    return {
        "project_name": project_name,
        "timeline_name": timeline_name,
        "otio_imported": True,
        "project_saved": True,
    }
