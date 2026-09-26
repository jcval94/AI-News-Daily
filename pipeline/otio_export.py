from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import opentimelineio as otio
from pipeline.schema_validation import validate_payload


SCHEMA_VERSION = 1
_METADATA_NS = "ai_news_daily"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing virtual timeline: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid virtual timeline JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("virtual_timeline.json must contain an object")
    return payload


def _frames(seconds: float, rate: float) -> int:
    return max(0, int(round(float(seconds) * float(rate))))


def _rt_from_seconds(seconds: float, rate: float) -> otio.opentime.RationalTime:
    return otio.opentime.RationalTime(_frames(seconds, rate), rate)


def _time_range(duration_seconds: float, rate: float) -> otio.opentime.TimeRange:
    return otio.opentime.TimeRange(
        start_time=otio.opentime.RationalTime(0, rate),
        duration=_rt_from_seconds(duration_seconds, rate),
    )


def _metadata(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _metadata(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_metadata(item) for item in value]
    return str(value)


def _clip_metadata(clip: dict[str, Any], track_id: str) -> dict[str, Any]:
    extension = (clip.get("source") or {}).get("media_provenance")
    if extension is not None:
        validate_payload(extension, "media_provenance.schema.json")
    return {
        _METADATA_NS: {
            "schema_version": SCHEMA_VERSION,
            "track_id": track_id,
            "clip_id": str(clip.get("clip_id", "") or ""),
            "kind": str(clip.get("kind", "") or ""),
            "status": str(clip.get("status", "") or ""),
            "take_id": clip.get("take_id"),
            "cue_id": clip.get("cue_id"),
            "replace_key": clip.get("replace_key"),
            "timeline_start_seconds": float(clip.get("timeline_start_seconds", 0) or 0),
            "timeline_end_seconds": float(clip.get("timeline_end_seconds", 0) or 0),
            "source": _metadata(clip.get("source", {})),
            "section": _metadata(clip.get("section", {})),
            "director": _metadata(clip.get("director", {})),
            "replacement": _metadata(clip.get("replacement", {})),
            "script_anchor": _metadata(clip.get("script_anchor", {})),
        }
    }


def _media_reference(
    clip: dict[str, Any],
    *,
    output_dir: Path,
) -> otio.schema.MediaReference:
    source = clip.get("source", {}) if isinstance(clip.get("source"), dict) else {}
    media_file = str(source.get("media_file", "") or "").strip()
    logical_media_path = str(source.get("logical_media_path", "") or "").strip()
    common_metadata = {
        _METADATA_NS: {
            "clip_id": str(clip.get("clip_id", "") or ""),
            "take_id": clip.get("take_id"),
            "cue_id": clip.get("cue_id"),
            "replace_key": clip.get("replace_key"),
            "source": _metadata(source),
        }
    }
    if media_file:
        target = (logical_media_path or media_file).replace("\\", "/")
        return otio.schema.ExternalReference(
            target_url=target,
            metadata=common_metadata,
        )
    return otio.schema.MissingReference(
        name=f"Missing · {clip.get('take_id') or clip.get('cue_id') or clip.get('clip_id')}",
        metadata=common_metadata,
    )


def _make_clip(
    clip: dict[str, Any],
    *,
    track_id: str,
    rate: float,
    output_dir: Path,
) -> otio.schema.Clip:
    duration = float(clip.get("duration_seconds", 0) or 0)
    if duration <= 0:
        raise ValueError(f"OTIO clip has non-positive duration: {clip.get('clip_id')}")
    result = otio.schema.Clip(
        name=str(clip.get("name", "") or clip.get("clip_id", "") or "clip"),
        source_range=_time_range(duration, rate),
        metadata=_clip_metadata(clip, track_id),
    )
    result.media_reference = _media_reference(clip, output_dir=output_dir)
    return result


def _gap(seconds: float, rate: float, *, reason: str) -> otio.schema.Gap:
    return otio.schema.Gap(
        name=reason,
        source_range=_time_range(seconds, rate),
        metadata={_METADATA_NS: {"kind": "timeline_gap", "reason": reason}},
    )


def _track_kind(kind: str) -> str:
    return (
        otio.schema.TrackKind.Audio
        if kind in {"dialogue", "audio", "music", "sfx"}
        else otio.schema.TrackKind.Video
    )


def _build_track(
    track_payload: dict[str, Any],
    *,
    timeline_duration: float,
    rate: float,
    output_dir: Path,
) -> otio.schema.Track:
    track_id = str(track_payload.get("track_id", "") or "")
    track = otio.schema.Track(
        name=f"{track_id} · {track_payload.get('name', '')}".strip(),
        kind=_track_kind(str(track_payload.get("kind", "") or "")),
        metadata={
            _METADATA_NS: {
                "track_id": track_id,
                "kind": str(track_payload.get("kind", "") or ""),
            }
        },
    )
    clips = sorted(
        [item for item in track_payload.get("clips", []) if isinstance(item, dict)],
        key=lambda item: float(item.get("timeline_start_seconds", 0) or 0),
    )
    cursor = 0.0
    for clip in clips:
        start = float(clip.get("timeline_start_seconds", 0) or 0)
        end = float(clip.get("timeline_end_seconds", start) or start)
        if start < cursor - 0.02:
            raise ValueError(
                f"Track {track_id} contains overlapping clips near {clip.get('clip_id')}"
            )
        if start > cursor + 0.02:
            track.append(_gap(start - cursor, rate, reason="intentional timeline gap"))
        track.append(
            _make_clip(
                clip,
                track_id=track_id,
                rate=rate,
                output_dir=output_dir,
            )
        )
        cursor = end
    if not clips and timeline_duration > 0:
        track.append(_gap(timeline_duration, rate, reason="empty reserved track"))
    elif cursor < timeline_duration - 0.02:
        track.append(_gap(timeline_duration - cursor, rate, reason="tail gap"))
    return track


def _marker(marker: dict[str, Any], rate: float) -> otio.schema.Marker:
    position = float(marker.get("timeline_seconds", 0) or 0)
    return otio.schema.Marker(
        name=str(marker.get("label", "") or marker.get("marker_id", "") or "marker"),
        marked_range=otio.opentime.TimeRange(
            start_time=_rt_from_seconds(position, rate),
            duration=otio.opentime.RationalTime(0, rate),
        ),
        metadata={
            _METADATA_NS: {
                "marker_id": str(marker.get("marker_id", "") or ""),
                "kind": str(marker.get("kind", "") or ""),
                "take_id": marker.get("take_id"),
                "section_key": marker.get("section_key"),
                "timeline_seconds": position,
            }
        },
    )


def build_otio_timeline(
    virtual_timeline: dict[str, Any],
    *,
    output_dir: Path,
) -> otio.schema.Timeline:
    if int(virtual_timeline.get("schema_version", 0) or 0) != 1:
        raise ValueError("Unsupported virtual timeline schema_version")
    episode_date = str(virtual_timeline.get("episode_date", "") or "").strip()
    if not episode_date:
        raise ValueError("virtual_timeline.json requires episode_date")

    timing = virtual_timeline.get("timing", {})
    fmt = virtual_timeline.get("format", {})
    rate = float(fmt.get("frame_rate_fps", timing.get("frame_rate_fps", 0)) or 0)
    duration = float(timing.get("duration_seconds", 0) or 0)
    if rate <= 0:
        raise ValueError("Virtual timeline requires positive frame_rate_fps")
    if duration <= 0:
        raise ValueError("Virtual timeline requires positive duration_seconds")

    timeline = otio.schema.Timeline(
        name=f"AI News Daily · {episode_date}",
        global_start_time=otio.opentime.RationalTime(0, rate),
        metadata={
            _METADATA_NS: {
                "schema_version": SCHEMA_VERSION,
                "episode_date": episode_date,
                "status": str(virtual_timeline.get("status", "") or ""),
                "format": _metadata(fmt),
                "timing": _metadata(timing),
                "editing_style": _metadata(virtual_timeline.get("editing_style", {})),
                "replacement_contract": _metadata(
                    virtual_timeline.get("replacement_contract", {})
                ),
                "readiness": _metadata(virtual_timeline.get("readiness", {})),
                "sources": _metadata(virtual_timeline.get("sources", {})),
            }
        },
    )

    seen_track_ids: set[str] = set()
    for track_payload in virtual_timeline.get("tracks", []):
        if not isinstance(track_payload, dict):
            continue
        track_id = str(track_payload.get("track_id", "") or "")
        if not track_id:
            raise ValueError("Virtual timeline track missing track_id")
        if track_id in seen_track_ids:
            raise ValueError(f"Duplicate virtual timeline track_id={track_id}")
        seen_track_ids.add(track_id)
        timeline.tracks.append(
            _build_track(
                track_payload,
                timeline_duration=duration,
                rate=rate,
                output_dir=output_dir,
            )
        )

    if not seen_track_ids:
        raise ValueError("Virtual timeline contains no tracks")

    for marker in virtual_timeline.get("markers", []):
        if isinstance(marker, dict):
            timeline.tracks.markers.append(_marker(marker, rate))

    return timeline


def _track_id(track: otio.schema.Track) -> str:
    meta = track.metadata.get(_METADATA_NS, {}) if track.metadata else {}
    return str(meta.get("track_id", "") or "")


def _timeline_seconds(timeline: otio.schema.Timeline) -> float:
    duration = timeline.duration()
    return float(duration.value) / float(duration.rate)


def validate_roundtrip(
    *,
    source_payload: dict[str, Any],
    timeline: otio.schema.Timeline,
) -> dict[str, Any]:
    expected_duration = float(source_payload.get("timing", {}).get("duration_seconds", 0) or 0)
    actual_duration = _timeline_seconds(timeline)
    rate = float(
        source_payload.get("format", {}).get(
            "frame_rate_fps",
            source_payload.get("timing", {}).get("frame_rate_fps", 0),
        )
        or 0
    )
    tolerance = 1.0 / max(rate, 1.0) + 1e-6
    if abs(actual_duration - expected_duration) > tolerance:
        raise ValueError(
            f"OTIO duration mismatch: expected {expected_duration:.3f}s, got {actual_duration:.3f}s"
        )

    expected_tracks = [
        str(item.get("track_id", "") or "")
        for item in source_payload.get("tracks", [])
        if isinstance(item, dict)
    ]
    actual_tracks = [_track_id(track) for track in timeline.tracks]
    if actual_tracks != expected_tracks:
        raise ValueError(
            f"OTIO track order mismatch: expected {expected_tracks}, got {actual_tracks}"
        )

    expected_markers = len(
        [item for item in source_payload.get("markers", []) if isinstance(item, dict)]
    )
    actual_markers = len(timeline.tracks.markers)
    if actual_markers != expected_markers:
        raise ValueError(
            f"OTIO marker count mismatch: expected {expected_markers}, got {actual_markers}"
        )

    expected_clips = sum(
        len([clip for clip in track.get("clips", []) if isinstance(clip, dict)])
        for track in source_payload.get("tracks", [])
        if isinstance(track, dict)
    )
    actual_clips = sum(
        1
        for track in timeline.tracks
        for item in track
        if isinstance(item, otio.schema.Clip)
    )
    if actual_clips != expected_clips:
        raise ValueError(
            f"OTIO clip count mismatch: expected {expected_clips}, got {actual_clips}"
        )

    return {
        "valid": True,
        "duration_seconds": round(actual_duration, 3),
        "track_ids": actual_tracks,
        "clip_count": actual_clips,
        "marker_count": actual_markers,
    }


def write_otio(
    *,
    episode_dir: Path,
) -> tuple[Path, Path]:
    source_path = episode_dir / "virtual_timeline.json"
    payload = _read_json(source_path)
    timeline = build_otio_timeline(payload, output_dir=episode_dir)

    destination = episode_dir / "timeline.otio"
    otio.adapters.write_to_file(timeline, str(destination), adapter_name="otio_json")

    reloaded = otio.adapters.read_from_file(str(destination), adapter_name="otio_json")
    validation = validate_roundtrip(source_payload=payload, timeline=reloaded)
    validation.update(
        {
            "source": str(source_path),
            "output": str(destination),
            "adapter": "otio_json",
            "opentimelineio_version": getattr(otio, "__version__", "unknown"),
            "frame_accurate": False,
            "requires_recording_retime": True,
        }
    )
    validation_path = episode_dir / "timeline_otio_validation.json"
    validation_path.write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination, validation_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export virtual timeline to native OpenTimelineIO")
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--scripts-dir", default="scripts")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    episode_dir = Path(args.scripts_dir) / args.target_date
    otio_path, validation_path = write_otio(episode_dir=episode_dir)
    print(
        json.dumps(
            {
                "timeline_otio": str(otio_path),
                "validation": str(validation_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
