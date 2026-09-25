from __future__ import annotations

import argparse
import hashlib
import json
import re
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(value: str, fallback: str) -> str:
    value = str(value or "").strip().lower()
    value = (
        value.replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u").replace("ü", "u").replace("ñ", "n")
    )
    value = re.sub(r"[^a-z0-9_-]+", "_", value).strip("_")
    return value or fallback


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _draw_slate(
    path: Path,
    *,
    width: int,
    height: int,
    eyebrow: str,
    title: str,
    body: list[str],
    footer: str,
    kind: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bg = (22, 22, 22) if kind == "presenter" else (16, 16, 16)
    accent = (210, 210, 210) if kind == "presenter" else (145, 145, 145)
    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)

    margin = max(28, width // 24)
    draw.rectangle((margin, margin, margin + max(8, width // 180), height - margin), fill=accent)
    x = margin + max(28, width // 45)
    usable = width - x - margin

    eyebrow_font = _font(max(18, width // 55))
    title_font = _font(max(28, width // 30))
    body_font = _font(max(20, width // 48))
    footer_font = _font(max(16, width // 65))

    draw.text((x, margin + 12), eyebrow.upper(), font=eyebrow_font, fill=(170, 170, 170))
    title_lines = textwrap.wrap(title, width=max(18, int(usable / max(14, width // 30))))
    y = margin + max(60, height // 10)
    draw.multiline_text((x, y), "\n".join(title_lines[:3]), font=title_font, fill=(245, 245, 245), spacing=8)
    title_box = draw.multiline_textbbox((x, y), "\n".join(title_lines[:3]), font=title_font, spacing=8)
    y = title_box[3] + max(24, height // 24)

    for line in body:
        wrapped = textwrap.wrap(str(line), width=max(28, int(usable / max(10, width // 48))))
        text = "\n".join(wrapped[:4])
        draw.multiline_text((x, y), text, font=body_font, fill=(195, 195, 195), spacing=6)
        box = draw.multiline_textbbox((x, y), text, font=body_font, spacing=6)
        y = box[3] + max(16, height // 40)
        if y > height - margin - 100:
            break

    draw.text((x, height - margin - max(30, height // 24)), footer, font=footer_font, fill=(135, 135, 135))
    image.save(path, format="PNG", optimize=True)


def _logical_path(episode_date: str, relative: Path) -> str:
    return f"scripts/{episode_date}/placeholder_media/{relative.as_posix()}"


def build_placeholder_manifest(
    *,
    virtual_timeline: dict[str, Any],
    output_dir: Path,
    width: int = 1280,
    height: int = 720,
) -> dict[str, Any]:
    if width < 320 or height < 180:
        raise ValueError("Placeholder canvas must be at least 320x180")
    episode_date = str(virtual_timeline.get("episode_date", "") or "").strip()
    if not episode_date:
        raise ValueError("virtual_timeline.json requires episode_date")

    tracks = {
        str(item.get("track_id", "") or ""): item
        for item in virtual_timeline.get("tracks", [])
        if isinstance(item, dict)
    }
    v1 = tracks.get("V1", {})
    v2 = tracks.get("V2", {})

    records: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    for clip in v1.get("clips", []) if isinstance(v1, dict) else []:
        if not isinstance(clip, dict):
            continue
        take_id = str(clip.get("take_id", "") or "").strip()
        replace_key = str(clip.get("replace_key", "") or take_id).strip()
        if not take_id or not replace_key:
            raise ValueError("V1 virtual A-roll clip requires take_id/replace_key")
        key = f"take:{replace_key}"
        if key in seen_keys:
            raise ValueError(f"Duplicate presenter placeholder key={key}")
        seen_keys.add(key)
        section = clip.get("section", {}) if isinstance(clip.get("section"), dict) else {}
        rel = Path("v1") / f"{_slug(take_id, 'take')}.png"
        physical = output_dir / rel
        _draw_slate(
            physical,
            width=width,
            height=height,
            eyebrow="JC VIRTUAL A-ROLL",
            title=take_id,
            body=[
                str(section.get("section_label", "") or section.get("section_key", "") or "Presenter"),
                f"Duración estimada: {float(clip.get('duration_seconds', 0) or 0):.1f} s",
                "Reemplazar por la toma real con el mismo take_id.",
            ],
            footer="PRE-RECORDING PLACEHOLDER · NO ES MATERIAL FINAL",
            kind="presenter",
        )
        records.append({
            "placeholder_id": key,
            "kind": "presenter",
            "track_id": "V1",
            "clip_id": str(clip.get("clip_id", "") or ""),
            "take_id": take_id,
            "cue_id": None,
            "replace_key": replace_key,
            "timeline_start_seconds": float(clip.get("timeline_start_seconds", 0) or 0),
            "timeline_end_seconds": float(clip.get("timeline_end_seconds", 0) or 0),
            "duration_seconds": float(clip.get("duration_seconds", 0) or 0),
            "file": rel.as_posix(),
            "logical_repo_path": _logical_path(episode_date, rel),
            "sha256": _sha256(physical),
            "status": "generated",
        })

    for clip in v2.get("clips", []) if isinstance(v2, dict) else []:
        if not isinstance(clip, dict) or clip.get("status") != "placeholder":
            continue
        cue_id = str(clip.get("cue_id", "") or "").strip()
        if not cue_id:
            raise ValueError("V2 media placeholder requires cue_id")
        key = f"cue:{cue_id}"
        if key in seen_keys:
            raise ValueError(f"Duplicate media placeholder key={key}")
        seen_keys.add(key)
        director = clip.get("director", {}) if isinstance(clip.get("director"), dict) else {}
        source = clip.get("source", {}) if isinstance(clip.get("source"), dict) else {}
        rel = Path("v2") / f"{_slug(cue_id, 'cue')}.png"
        physical = output_dir / rel
        query = str(clip.get("name", "") or cue_id)
        _draw_slate(
            physical,
            width=width,
            height=height,
            eyebrow="B-ROLL PLACEHOLDER",
            title=cue_id,
            body=[
                f"Rol: {str(director.get('visual_role', '') or 'media')}",
                query,
                f"Duración: {float(clip.get('duration_seconds', 0) or 0):.1f} s",
                "Bloqueos: " + ", ".join(str(x) for x in source.get("blockers", []) if str(x)),
            ],
            footer="REEMPLAZAR CON ASSET RESUELTO · NO PUBLICAR ESTE SLATE",
            kind="media",
        )
        records.append({
            "placeholder_id": key,
            "kind": "media",
            "track_id": "V2",
            "clip_id": str(clip.get("clip_id", "") or ""),
            "take_id": None,
            "cue_id": cue_id,
            "replace_key": cue_id,
            "timeline_start_seconds": float(clip.get("timeline_start_seconds", 0) or 0),
            "timeline_end_seconds": float(clip.get("timeline_end_seconds", 0) or 0),
            "duration_seconds": float(clip.get("duration_seconds", 0) or 0),
            "file": rel.as_posix(),
            "logical_repo_path": _logical_path(episode_date, rel),
            "sha256": _sha256(physical),
            "status": "generated",
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "episode_date": episode_date,
        "status": "pre_recording_placeholder_media",
        "canvas": {
            "width": width,
            "height": height,
            "purpose": "lightweight_proxy_slates_for_nle",
            "timeline_resolution": str(
                (virtual_timeline.get("format", {}) or {}).get("resolution", "")
            ),
        },
        "policy": {
            "presenter_placeholders_for_every_v1_take": True,
            "media_placeholders_only_for_unresolved_v2_cues": True,
            "resolved_media_is_never_replaced_by_placeholder": True,
            "placeholder_is_never_publishable_media": True,
        },
        "summary": {
            "placeholder_count": len(records),
            "presenter_placeholder_count": sum(1 for item in records if item["kind"] == "presenter"),
            "media_placeholder_count": sum(1 for item in records if item["kind"] == "media"),
        },
        "items": records,
    }


def write_placeholder_media(
    *,
    episode_dir: Path,
    width: int = 1280,
    height: int = 720,
) -> tuple[Path, Path]:
    timeline_path = episode_dir / "virtual_timeline.json"
    if not timeline_path.is_file():
        raise FileNotFoundError(f"Missing virtual timeline: {timeline_path}")
    virtual = _read_json(timeline_path)
    output_dir = episode_dir / "placeholder_media"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_placeholder_manifest(
        virtual_timeline=virtual,
        output_dir=output_dir,
        width=width,
        height=height,
    )
    validate_payload(manifest, "placeholder_media.schema.json")
    destination = output_dir / "placeholder_manifest.json"
    destination.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_dir, destination


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate lightweight NLE placeholder slates")
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--scripts-dir", default="scripts")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    episode_dir = Path(args.scripts_dir) / args.target_date
    directory, manifest = write_placeholder_media(
        episode_dir=episode_dir,
        width=args.width,
        height=args.height,
    )
    print(json.dumps({"placeholder_media": str(directory), "manifest": str(manifest)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
