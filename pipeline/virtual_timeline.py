from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
_EPSILON = 0.02


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _round(value: float) -> float:
    return round(max(0.0, float(value)), 3)


def _json_sha256(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate_sources(recording_pack: dict[str, Any], edit_manifest: dict[str, Any]) -> None:
    episode_date = str(recording_pack.get("episode_date", "") or "")
    edit_date = str(edit_manifest.get("episode_date", "") or "")
    if not episode_date:
        raise ValueError("recording_pack.json requires episode_date")
    if edit_date and edit_date != episode_date:
        raise ValueError(
            f"edit_manifest episode_date={edit_date} does not match recording_pack={episode_date}"
        )

    takes = recording_pack.get("takes", [])
    if not isinstance(takes, list) or not takes:
        raise ValueError("recording_pack.json requires at least one take")

    seen: set[str] = set()
    previous_end = 0.0
    for take in takes:
        if not isinstance(take, dict):
            raise ValueError("recording_pack takes must be objects")
        take_id = str(take.get("take_id", "") or "").strip()
        if not take_id:
            raise ValueError("recording_pack take missing take_id")
        if take_id in seen:
            raise ValueError(f"Duplicate recording take_id={take_id}")
        seen.add(take_id)
        start = float(take.get("estimated_start_seconds", 0) or 0)
        end = float(take.get("estimated_end_seconds", start) or start)
        if end <= start + _EPSILON:
            raise ValueError(f"Invalid duration for take_id={take_id}")
        if abs(start - previous_end) > 0.05:
            raise ValueError(
                f"Recording takes are not contiguous before {take_id}: "
                f"expected {previous_end:.3f}, got {start:.3f}"
            )
        previous_end = end

    rec_style = recording_pack.get("editing_style", {})
    edit_style = edit_manifest.get("editing_style", {})
    if (
        isinstance(rec_style, dict)
        and isinstance(edit_style, dict)
        and rec_style.get("applied") is True
        and edit_style.get("applied") is True
    ):
        rec_hash = str(rec_style.get("sha256", "") or "")
        edit_hash = str(edit_style.get("sha256", "") or "")
        if rec_hash and edit_hash and rec_hash != edit_hash:
            raise ValueError("Recording Pack and edit manifest use different editing-style fingerprints")


def _group_media_cues(edit_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for segment in edit_manifest.get("timeline", []) if isinstance(edit_manifest, dict) else []:
        if not isinstance(segment, dict) or segment.get("mode") != "media":
            continue
        cue_id = str(segment.get("cue_id", "") or "").strip()
        if not cue_id:
            cue_id = f"anonymous_{len(order) + 1:03d}"
        start = float(segment.get("start_seconds", 0) or 0)
        end = float(segment.get("end_seconds", start) or start)
        if end <= start + _EPSILON:
            continue
        if cue_id not in grouped:
            grouped[cue_id] = {
                "cue_id": cue_id,
                "start_seconds": start,
                "end_seconds": end,
                "segment_ids": [str(segment.get("segment_id", "") or "")],
                "section": dict(segment.get("section", {}) or {}),
                "script_anchor": dict(segment.get("script_anchor", {}) or {}),
                "director": dict(segment.get("director", {}) or {}),
                "media": dict(segment.get("media", {}) or {}),
            }
            order.append(cue_id)
        else:
            item = grouped[cue_id]
            item["start_seconds"] = min(float(item["start_seconds"]), start)
            item["end_seconds"] = max(float(item["end_seconds"]), end)
            item["segment_ids"].append(str(segment.get("segment_id", "") or ""))
    return [grouped[key] for key in order]


def _presenter_track(recording_pack: dict[str, Any]) -> list[dict[str, Any]]:
    clips: list[dict[str, Any]] = []
    for position, take in enumerate(recording_pack.get("takes", []), start=1):
        start = float(take.get("estimated_start_seconds", 0) or 0)
        end = float(take.get("estimated_end_seconds", start) or start)
        take_id = str(take.get("take_id", "") or "")
        clips.append(
            {
                "clip_id": f"aroll_{position:03d}_{take_id}",
                "kind": "virtual_a_roll",
                "status": "placeholder",
                "take_id": take_id,
                "name": f"JC · {take_id}",
                "timeline_start_seconds": _round(start),
                "timeline_end_seconds": _round(end),
                "duration_seconds": _round(end - start),
                "replace_key": take_id,
                "source": {
                    "type": "generated_placeholder",
                    "media_file": None,
                    "recorded_media_required": True,
                },
                "section": {
                    "section_key": str(take.get("section_key", "") or ""),
                    "section_kind": str(take.get("section_kind", "") or ""),
                    "beat_id": take.get("beat_id"),
                    "beat_kind": take.get("beat_kind"),
                    "section_label": str(take.get("section_label", "") or ""),
                },
                "spoken_text": str(take.get("spoken_text", "") or ""),
                "delivery": dict(take.get("delivery", {}) or {}),
                "replacement": {
                    "strategy": "align_by_take_id_then_retime_timeline",
                    "keep_virtual_clip_until_alignment": True,
                    "preserve_take_identity": True,
                },
            }
        )
    return clips


def _media_track(edit_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    clips: list[dict[str, Any]] = []
    for position, cue in enumerate(_group_media_cues(edit_manifest), start=1):
        start = float(cue["start_seconds"])
        end = float(cue["end_seconds"])
        media = cue.get("media", {}) if isinstance(cue.get("media"), dict) else {}
        director = cue.get("director", {}) if isinstance(cue.get("director"), dict) else {}
        usable = bool(media.get("usable_for_edit") is True)
        file_path = str(media.get("file", "") or "").strip()
        role = str(director.get("visual_role", "") or "media")
        query = str(media.get("visual_query", "") or "").strip()
        name = query or str(media.get("on_screen_text", "") or "").strip() or cue["cue_id"]
        blockers = [str(value) for value in media.get("blockers", []) if str(value)]
        clips.append(
            {
                "clip_id": f"broll_{position:03d}_{cue['cue_id']}",
                "kind": "media_asset" if usable else "media_placeholder",
                "status": "resolved" if usable else "placeholder",
                "cue_id": cue["cue_id"],
                "name": name,
                "timeline_start_seconds": _round(start),
                "timeline_end_seconds": _round(end),
                "duration_seconds": _round(end - start),
                "source": {
                    "type": "file" if usable else "generated_placeholder",
                    "media_file": file_path if usable else None,
                    "asset_type": str(media.get("asset_type", "") or ""),
                    "preferred_asset_type": str(media.get("preferred_asset_type", "") or ""),
                    "provider": str(media.get("provider", "") or ""),
                    "license": str(media.get("license", "") or ""),
                    "usable_for_edit": usable,
                    "blockers": blockers,
                },
                "director": {
                    "visual_role": role,
                    "intent": str(director.get("intent", "") or ""),
                    "treatment": str(director.get("treatment", "") or ""),
                    "transition_in": str(director.get("transition_in", "") or ""),
                    "transition_out": str(director.get("transition_out", "") or ""),
                    "pacing": str(director.get("pacing", "") or ""),
                    "note": str(director.get("note", "") or ""),
                },
                "section": dict(cue.get("section", {}) or {}),
                "script_anchor": dict(cue.get("script_anchor", {}) or {}),
                "edit_manifest_segment_ids": list(cue.get("segment_ids", []) or []),
            }
        )
    return clips


def _graphics_track(media_clips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clips: list[dict[str, Any]] = []
    for item in media_clips:
        cue_id = str(item.get("cue_id", "") or "")
        # on_screen_text is not copied into the compact media-track contract above;
        # recover only intentional labels from the name when a future generator marks them.
        # V3 stays sparse by default so it does not duplicate narration.
        if item.get("director", {}).get("visual_role") == "evidence":
            continue
        _ = cue_id
    return clips


def _track_summary(clips: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "clip_count": len(clips),
        "placeholder_count": sum(1 for item in clips if item.get("status") == "placeholder"),
        "resolved_count": sum(1 for item in clips if item.get("status") == "resolved"),
        "covered_seconds": _round(sum(float(item.get("duration_seconds", 0) or 0) for item in clips)),
    }


def build_virtual_timeline(
    *,
    recording_pack: dict[str, Any],
    edit_manifest: dict[str, Any],
) -> dict[str, Any]:
    _validate_sources(recording_pack, edit_manifest)
    takes = recording_pack["takes"]
    presenter_clips = _presenter_track(recording_pack)
    media_clips = _media_track(edit_manifest)
    graphics_clips = _graphics_track(media_clips)

    duration = max(float(take.get("estimated_end_seconds", 0) or 0) for take in takes)
    script_duration = float(
        (edit_manifest.get("timing", {}) or {}).get("duration_seconds", 0) or 0
    )
    capture = (
        recording_pack.get("capture_recommendation", {})
        if isinstance(recording_pack.get("capture_recommendation"), dict)
        else {}
    )
    frame_rate = int(capture.get("frame_rate_fps", 30) or 30)
    if frame_rate <= 0:
        raise ValueError("Recording Pack frame_rate_fps must be positive")
    resolution = str(capture.get("resolution", "") or "3840x2160")
    audio_sample_rate = int(capture.get("audio_sample_rate_hz", 48000) or 48000)
    if audio_sample_rate <= 0:
        raise ValueError("Recording Pack audio_sample_rate_hz must be positive")
    blockers: set[str] = {
        "recorded_media_required",
        "recording_retime_required",
    }
    for clip in media_clips:
        for blocker in clip.get("source", {}).get("blockers", []):
            if blocker:
                blockers.add(str(blocker))

    style = (
        dict(recording_pack.get("editing_style", {}) or {})
        if isinstance(recording_pack.get("editing_style"), dict)
        else {"applied": False}
    )

    markers: list[dict[str, Any]] = []
    seen_sections: set[str] = set()
    for take in takes:
        take_id = str(take.get("take_id", "") or "")
        start = _round(float(take.get("estimated_start_seconds", 0) or 0))
        markers.append({
            "marker_id": f"take_{take_id}",
            "kind": "take",
            "timeline_seconds": start,
            "label": take_id,
            "take_id": take_id,
        })
        section_key = str(take.get("section_key", "") or "")
        if section_key and section_key not in seen_sections:
            seen_sections.add(section_key)
            markers.append({
                "marker_id": f"section_{len(seen_sections):02d}",
                "kind": "section",
                "timeline_seconds": start,
                "label": str(take.get("section_label", "") or section_key),
                "section_key": section_key,
            })
    markers.sort(key=lambda item: (float(item["timeline_seconds"]), 0 if item["kind"] == "section" else 1))

    tracks = [
        {
            "track_id": "V4",
            "kind": "titles",
            "name": "Titles",
            "clips": [],
        },
        {
            "track_id": "V3",
            "kind": "graphics",
            "name": "Graphics",
            "clips": graphics_clips,
        },
        {
            "track_id": "V2",
            "kind": "b_roll",
            "name": "B-roll / visual evidence",
            "clips": media_clips,
        },
        {
            "track_id": "V1",
            "kind": "presenter",
            "name": "JC virtual A-roll",
            "clips": presenter_clips,
        },
        {
            "track_id": "A1",
            "kind": "dialogue",
            "name": "JC dialogue placeholder",
            "clips": [
                {
                    "clip_id": f"audio_{item['take_id']}",
                    "kind": "virtual_dialogue",
                    "status": "placeholder",
                    "take_id": item["take_id"],
                    "name": item["name"],
                    "timeline_start_seconds": item["timeline_start_seconds"],
                    "timeline_end_seconds": item["timeline_end_seconds"],
                    "duration_seconds": item["duration_seconds"],
                    "replace_key": item["replace_key"],
                    "source": {
                        "type": "generated_placeholder",
                        "media_file": None,
                        "recorded_media_required": True,
                    },
                }
                for item in presenter_clips
            ],
        },
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "episode_date": str(recording_pack.get("episode_date", "") or ""),
        "status": "pre_recording_virtual_timeline",
        "timing": {
            "basis": "estimated_recording_pack_words",
            "duration_seconds": _round(duration),
            "approved_script_duration_seconds": _round(script_duration),
            "post_script_duration_seconds": _round(max(0.0, duration - script_duration)),
            "frame_rate_fps": frame_rate,
            "frame_accurate": False,
            "requires_recording_retime": True,
        },
        "sources": {
            "recording_pack": f"scripts/{recording_pack.get('episode_date')}/recording_pack.json",
            "edit_manifest": f"multimedia/{recording_pack.get('episode_date')}/edit_manifest.json",
            "recording_pack_sha256": _json_sha256(recording_pack),
            "edit_manifest_sha256": _json_sha256(edit_manifest),
        },
        "editing_style": style,
        "format": {
            "resolution": resolution,
            "frame_rate_fps": frame_rate,
            "audio_sample_rate_hz": audio_sample_rate,
            "aspect_ratio": str(capture.get("aspect_ratio", "") or "16:9"),
        },
        "markers": markers,
        "replacement_contract": {
            "virtual_a_roll_authority": "take_id",
            "strategy": "replace_and_retime_after_alignment",
            "real_a_roll_may_change_duration": True,
            "retime_b_roll_after_alignment": True,
            "never_treat_estimated_seconds_as_source_timecode": True,
        },
        "readiness": {
            "virtual_timeline_contract_valid": True,
            "ready_for_virtual_preview": True,
            "ready_for_real_a_roll_replace": False,
            "ready_for_automated_nle_import": False,
            "blockers_for_final": sorted(blockers),
        },
        "summary": {
            "track_count": len(tracks),
            "take_count": len(presenter_clips),
            "media_cue_count": len(media_clips),
            "resolved_media_count": sum(1 for item in media_clips if item["status"] == "resolved"),
            "media_placeholder_count": sum(1 for item in media_clips if item["status"] == "placeholder"),
            "virtual_a_roll_seconds": _round(sum(item["duration_seconds"] for item in presenter_clips)),
            "media_overlay_seconds": _round(sum(item["duration_seconds"] for item in media_clips)),
        },
        "track_summaries": {
            track["track_id"]: _track_summary(track["clips"])
            for track in tracks
        },
        "tracks": tracks,
    }


def _safe_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def render_timeline_preview(payload: dict[str, Any]) -> str:
    data = _safe_payload(payload)
    title = html.escape(f"Virtual timeline — {payload.get('episode_date', '')}")
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
:root {{ --px-per-second: 8; --track-height: 68px; }}
* {{ box-sizing: border-box; }}
html,body {{ margin:0; background:#0a0a0a; color:#f3f3f3; font-family:Arial,Helvetica,sans-serif; }}
header {{ position:sticky; top:0; z-index:10; display:flex; gap:12px; align-items:center; flex-wrap:wrap; padding:12px 16px; background:#111; border-bottom:1px solid #2b2b2b; }}
button,input {{ font:inherit; }}
button {{ background:#202020; color:#fff; border:1px solid #3a3a3a; border-radius:8px; padding:7px 10px; }}
.meta {{ color:#aaa; font-size:13px; margin-left:auto; }}
#timeline {{ overflow:auto; height:calc(100vh - 58px); }}
#canvas {{ position:relative; min-height:100%; }}
.ruler {{ position:sticky; top:0; z-index:4; height:34px; background:#101010; border-bottom:1px solid #292929; margin-left:120px; }}
.tick {{ position:absolute; top:0; height:34px; border-left:1px solid #333; color:#888; font-size:11px; padding-left:4px; padding-top:4px; }}
.track {{ position:relative; height:var(--track-height); border-bottom:1px solid #242424; margin-left:120px; }}
.track-label {{ position:absolute; left:-120px; width:120px; height:100%; padding:10px; background:#111; border-right:1px solid #292929; color:#bbb; font-size:12px; }}
.clip {{ position:absolute; top:8px; height:50px; min-width:2px; overflow:hidden; border:1px solid #555; border-radius:6px; padding:5px 7px; font-size:11px; cursor:pointer; background:#1f1f1f; }}
.clip.presenter {{ background:#262626; }}
.clip.media_asset {{ background:#313131; }}
.clip.media_placeholder {{ background:#191919; border-style:dashed; }}
.clip.virtual_dialogue {{ height:32px; top:18px; }}
.clip .sub {{ color:#aaa; display:block; margin-top:3px; white-space:nowrap; }}
#inspector {{ position:fixed; right:16px; bottom:16px; width:min(430px,calc(100vw - 32px)); max-height:45vh; overflow:auto; padding:14px; background:#151515; border:1px solid #3b3b3b; border-radius:10px; display:none; z-index:20; }}
#inspector.visible {{ display:block; }}
pre {{ white-space:pre-wrap; word-break:break-word; color:#ddd; font-size:12px; margin:0; }}
.badge {{ padding:2px 6px; border:1px solid #444; border-radius:999px; font-size:11px; color:#bbb; }}
</style>
</head>
<body>
<header>
  <strong>Virtual timeline · {html.escape(str(payload.get("episode_date", "")))}</strong>
  <span class="badge">PRE-RECORDING</span>
  <label>Zoom <input id="zoom" type="range" min="2" max="30" value="8"></label>
  <button id="fit">Ajustar</button>
  <div class="meta" id="meta"></div>
</header>
<div id="timeline"><div id="canvas"><div class="ruler" id="ruler"></div><div id="tracks"></div></div></div>
<div id="inspector"><pre id="details"></pre></div>
<script>
const DATA={data};
const timeline=document.getElementById('timeline');
const canvas=document.getElementById('canvas');
const tracks=document.getElementById('tracks');
const ruler=document.getElementById('ruler');
const zoom=document.getElementById('zoom');
const inspector=document.getElementById('inspector');
const details=document.getElementById('details');
const duration=Number(DATA.timing?.duration_seconds||0);

function draw(){{
  const pps=Number(zoom.value);
  const width=Math.max(900,Math.ceil(duration*pps));
  canvas.style.width=(width+120)+'px';
  ruler.style.width=width+'px';
  ruler.innerHTML='';
  const step=duration>1200?120:duration>600?60:duration>180?30:10;
  for(let t=0;t<=duration;t+=step){{
    const el=document.createElement('div');
    el.className='tick';
    el.style.left=(t*pps)+'px';
    el.textContent=Math.floor(t/60)+':'+String(Math.round(t%60)).padStart(2,'0');
    ruler.appendChild(el);
  }}
  tracks.innerHTML='';
  (DATA.tracks||[]).forEach(track=>{{
    const row=document.createElement('div'); row.className='track'; row.style.width=width+'px';
    const label=document.createElement('div'); label.className='track-label'; label.textContent=track.track_id+' · '+track.name; row.appendChild(label);
    (track.clips||[]).forEach(clip=>{{
      const el=document.createElement('div');
      el.className='clip '+(clip.kind==='virtual_a_roll'?'presenter':clip.kind);
      el.style.left=(Number(clip.timeline_start_seconds||0)*pps)+'px';
      el.style.width=Math.max(3,Number(clip.duration_seconds||0)*pps)+'px';
      el.innerHTML='<strong>'+escapeHtml(clip.take_id||clip.cue_id||clip.name||clip.clip_id)+'</strong><span class="sub">'+escapeHtml(clip.status||'')+'</span>';
      el.title=clip.name||clip.clip_id;
      el.onclick=()=>{{details.textContent=JSON.stringify(clip,null,2);inspector.classList.add('visible')}};
      row.appendChild(el);
    }});
    tracks.appendChild(row);
  }});
  document.getElementById('meta').textContent =
    (DATA.summary?.take_count||0)+' takes · '+(DATA.summary?.media_cue_count||0)+' media cues · ~'+Math.round(duration/60)+' min';
}}
function escapeHtml(v){{return String(v||'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}}[c]))}}
zoom.oninput=draw;
document.getElementById('fit').onclick=()=>{{
  const available=Math.max(2,timeline.clientWidth-150);
  zoom.value=Math.max(2,Math.min(30,available/Math.max(duration,1)));
  draw(); timeline.scrollLeft=0;
}};
inspector.onclick=()=>inspector.classList.remove('visible');
draw();
</script>
</body>
</html>
"""


def write_virtual_timeline(
    *,
    episode_dir: Path,
    media_dir: Path,
) -> tuple[Path, Path]:
    recording_pack = _read_json(episode_dir / "recording_pack.json", {})
    edit_manifest = _read_json(media_dir / "edit_manifest.json", {})
    if not recording_pack:
        raise FileNotFoundError(f"Missing recording pack: {episode_dir / 'recording_pack.json'}")
    if not edit_manifest:
        raise FileNotFoundError(f"Missing edit manifest: {media_dir / 'edit_manifest.json'}")

    payload = build_virtual_timeline(
        recording_pack=recording_pack,
        edit_manifest=edit_manifest,
    )
    json_path = episode_dir / "virtual_timeline.json"
    html_path = episode_dir / "timeline_preview.html"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(render_timeline_preview(payload), encoding="utf-8")
    return json_path, html_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the pre-recording virtual A-roll timeline")
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--scripts-dir", default="scripts")
    parser.add_argument("--multimedia-dir", default="multimedia")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    episode_dir = Path(args.scripts_dir) / args.target_date
    media_dir = Path(args.multimedia_dir) / args.target_date
    paths = write_virtual_timeline(episode_dir=episode_dir, media_dir=media_dir)
    print(json.dumps({"virtual_timeline": str(paths[0]), "timeline_preview": str(paths[1])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
