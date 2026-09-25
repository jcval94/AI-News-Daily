from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pipeline.media_inspection import inspect_audio, inspect_media
from pipeline.schema_validation import validate_payload


SCHEMA_VERSION = 1
VIDEO_EXTENSIONS = {".mov", ".mp4", ".mxf", ".mkv", ".avi"}
AUDIO_EXTENSIONS = {".wav", ".m4a", ".aac", ".flac", ".mp3"}
_FILENAME_RE = re.compile(
    r"^(?P<take_id>[A-Za-z0-9][A-Za-z0-9_-]*?)__r(?P<retake>\d{2})(?:__(?P<label>[A-Za-z][A-Za-z0-9_-]*))?$"
)


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


def build_recording_ingest_contract(recording_pack: dict[str, Any]) -> dict[str, Any]:
    episode_date = str(recording_pack.get("episode_date", "") or "").strip()
    takes = [dict(item) for item in recording_pack.get("takes", []) if isinstance(item, dict)]
    if not episode_date or not takes:
        raise ValueError("recording_pack.json requires episode_date and takes")

    take_ids = [str(item.get("take_id", "") or "").strip() for item in takes]
    if any(not value for value in take_ids):
        raise ValueError("Every recording take requires take_id")
    if len(set(take_ids)) != len(take_ids):
        raise ValueError("recording_pack.json contains duplicate take_id values")

    capture = (
        recording_pack.get("capture_recommendation", {})
        if isinstance(recording_pack.get("capture_recommendation"), dict)
        else {}
    )
    protocol = (
        recording_pack.get("recording_protocol", {})
        if isinstance(recording_pack.get("recording_protocol"), dict)
        else {}
    )
    pre_roll = float(protocol.get("pre_roll_seconds", 2.0) or 2.0)
    post_roll = float(protocol.get("post_roll_seconds", 2.0) or 2.0)

    expected: list[dict[str, Any]] = []
    for take in takes:
        take_id = str(take["take_id"])
        spoken_seconds = float(take.get("estimated_duration_seconds", 0) or 0)
        expected.append(
            {
                "take_id": take_id,
                "section_label": str(take.get("section_label", "") or ""),
                "spoken_slate": str(take.get("spoken_slate", "") or f"TAKE {take_id}"),
                "expected_spoken_seconds": round(spoken_seconds, 3),
                "expected_capture_seconds": round(spoken_seconds + pre_roll + post_roll, 3),
                "video_required": True,
                "audio_requirement": "embedded_or_paired_external",
                "examples": {
                    "video_first_take": f"{take_id}__r01__camA.mov",
                    "video_retake": f"{take_id}__r02__camA.mov",
                    "external_audio": f"{take_id}__r01__audio.wav",
                },
            }
        )

    fps = int(capture.get("frame_rate_fps", 30) or 30)
    audio_rate = int(capture.get("audio_sample_rate_hz", 48000) or 48000)
    return {
        "schema_version": SCHEMA_VERSION,
        "episode_date": episode_date,
        "status": "awaiting_recorded_media",
        "sources": {
            "recording_pack": f"scripts/{episode_date}/recording_pack.json",
        },
        "storage": {
            "recommended_local_root": f"recordings/{episode_date}",
            "recommended_inbox": f"recordings/{episode_date}/inbox",
            "media_is_local_only": True,
            "never_commit_raw_recordings": True,
            "manifest_stores_relative_paths_only": True,
            "scanner_never_deletes_or_moves_source_files": True,
        },
        "naming": {
            "grammar": "<take_id>__r<NN>__<label>.<ext>",
            "retake_number_format": "two_digits_starting_at_01",
            "video_labels": ["camA", "camB", "cam1", "cam2", "main"],
            "audio_labels": ["audio", "lav", "mic", "micA", "micB"],
            "video_extensions": sorted(VIDEO_EXTENSIONS),
            "audio_extensions": sorted(AUDIO_EXTENSIONS),
            "case_sensitive_take_id": True,
            "examples": [
                f"{take_ids[0]}__r01__camA.mov",
                f"{take_ids[0]}__r02__camA.mov",
                f"{take_ids[0]}__r01__audio.wav",
            ],
        },
        "technical_policy": {
            "preferred_resolution": str(capture.get("resolution", "3840x2160") or "3840x2160"),
            "preferred_frame_rate_fps": fps,
            "preferred_audio_sample_rate_hz": audio_rate,
            "minimum_short_edge_px": 720,
            "minimum_usable_duration_ratio": 0.55,
            "long_capture_warning_ratio": 2.50,
            "preferred_camera_labels": ["camA", "cam1", "main", "camB", "cam2"],
            "external_audio_bonus": True,
            "embedded_audio_is_acceptable": True,
        },
        "selection_policy": {
            "authority": "technical_only_not_performance_or_script_accuracy",
            "retain_all_retakes": True,
            "never_delete_nonselected_retakes": True,
            "technical_preferred_is_provisional": True,
            "later_alignment_may_select_another_retake": True,
            "tie_breaker": "later_retake_after_equal_technical_score",
        },
        "future_alignment": {
            "stable_join_key": "take_id",
            "requires_transcription": True,
            "must_compare_transcript_to_recording_pack_spoken_text": True,
            "expected_output": f"scripts/{episode_date}/recording_alignment.json",
        },
        "readiness": {
            "contract_valid": True,
            "ready_for_scan": True,
            "ready_for_alignment": False,
            "blockers": ["recorded_media_required"],
        },
        "summary": {
            "expected_take_count": len(expected),
        },
        "expected_takes": expected,
    }


def render_ingest_instructions(contract: dict[str, Any]) -> str:
    date = str(contract.get("episode_date", "") or "")
    lines = [
        f"# Recording ingest — {date}",
        "",
        "## Regla principal",
        "",
        "No renombres por contenido libre. Usa siempre el take_id exacto del Recording Pack.",
        "",
        "Formato: <take_id>__r<NN>__<label>.<ext>",
        "",
        "Ejemplos:",
        "",
    ]
    for example in contract.get("naming", {}).get("examples", []):
        lines.append(f"- {example}")
    lines.extend(
        [
            "",
            "## Retakes",
            "",
            "- Empieza en r01.",
            "- Si repites una toma completa, incrementa r02, r03, etc.",
            "- No borres una toma anterior porque parezca peor.",
            "- El ingest escoge sólo un candidato técnico provisional; WhisperX/alignment decidirá después si otra toma respeta mejor el guion.",
            "",
            "## Audio",
            "",
            "- El video puede usar audio embebido.",
            "- Si tienes lavalier/mic externo, usa el mismo take_id y retake con audio.wav, lav.wav, etc.",
            "- Un take sin audio embebido sano y sin audio externo pareado no queda listo para alignment.",
            "",
            "## Carpeta recomendada",
            "",
            str(contract.get("storage", {}).get("recommended_inbox", "")),
            "",
            "Los archivos crudos permanecen fuera de Git. El scanner sólo lee, nunca mueve ni borra.",
            "",
            "## Comando futuro",
            "",
            "python -m pipeline.recording_ingest --target-date "
            + date
            + ' --input-dir "/ruta/a/recordings" --enforce',
            "",
        ]
    )
    return "\n".join(lines)


def write_ingest_contract(*, episode_dir: Path) -> tuple[Path, Path, dict[str, Any]]:
    pack_path = episode_dir / "recording_pack.json"
    if not pack_path.is_file():
        raise FileNotFoundError(f"Missing Recording Pack: {pack_path}")
    contract = build_recording_ingest_contract(_read_json(pack_path))
    validate_payload(contract, "recording_ingest_contract.schema.json")
    json_path = episode_dir / "recording_ingest_contract.json"
    md_path = episode_dir / "recording_ingest_instructions.md"
    json_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_ingest_instructions(contract), encoding="utf-8")
    return json_path, md_path, contract


def parse_capture_filename(path: Path) -> dict[str, Any] | None:
    suffix = path.suffix.lower()
    if suffix not in VIDEO_EXTENSIONS | AUDIO_EXTENSIONS:
        return None
    match = _FILENAME_RE.fullmatch(path.stem)
    if not match:
        return {
            "matched": False,
            "media_type": "video" if suffix in VIDEO_EXTENSIONS else "audio",
            "extension": suffix,
        }
    media_type = "video" if suffix in VIDEO_EXTENSIONS else "audio"
    label = str(match.group("label") or ("camA" if media_type == "video" else "audio"))
    return {
        "matched": True,
        "take_id": str(match.group("take_id")),
        "retake_number": int(match.group("retake")),
        "label": label,
        "media_type": media_type,
        "extension": suffix,
    }


def _duration_score(actual: float, expected: float) -> float:
    if expected <= 0 or actual <= 0:
        return 0.0
    return max(0.0, 1.0 - abs(actual - expected) / expected)


def _camera_rank(label: str, preferred: list[str]) -> int:
    try:
        return preferred.index(label)
    except ValueError:
        return len(preferred) + 1


def _select_video(
    videos: list[dict[str, Any]],
    *,
    expected_seconds: float,
    preferred_labels: list[str],
) -> dict[str, Any] | None:
    healthy = [item for item in videos if item.get("inspection", {}).get("ok")]
    if not healthy:
        return None

    def key(item: dict[str, Any]) -> tuple[float, int, int]:
        inspection = item["inspection"]
        pixels = int(inspection.get("width", 0) or 0) * int(inspection.get("height", 0) or 0)
        duration = float(inspection.get("duration_seconds", 0) or 0)
        duration_component = _duration_score(duration, expected_seconds)
        camera_component = max(
            0.0,
            1.0 - 0.15 * _camera_rank(str(item.get("label", "")), preferred_labels),
        )
        embedded = 1.0 if inspection.get("has_audio_stream") else 0.0
        score = (
            duration_component * 60.0
            + min(1.0, pixels / float(3840 * 2160)) * 25.0
            + camera_component * 10.0
            + embedded * 5.0
        )
        return (
            score,
            pixels,
            -_camera_rank(str(item.get("label", "")), preferred_labels),
        )

    return max(healthy, key=key)


def _select_audio(
    audios: list[dict[str, Any]],
    *,
    expected_seconds: float,
) -> dict[str, Any] | None:
    healthy = [item for item in audios if item.get("inspection", {}).get("ok")]
    if not healthy:
        return None
    return max(
        healthy,
        key=lambda item: (
            int(item["inspection"].get("sample_rate_hz", 0) or 0),
            int(item["inspection"].get("channels", 0) or 0),
            _duration_score(
                float(item["inspection"].get("duration_seconds", 0) or 0),
                expected_seconds,
            ),
        ),
    )


def scan_recordings(
    *,
    contract: dict[str, Any],
    input_dir: Path,
) -> dict[str, Any]:
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Recording input directory does not exist: {input_dir}")

    expected = {
        str(item["take_id"]): dict(item)
        for item in contract.get("expected_takes", [])
        if isinstance(item, dict)
    }
    policy = contract.get("technical_policy", {})
    preferred_labels = [str(x) for x in policy.get("preferred_camera_labels", [])]
    min_duration_ratio = float(policy.get("minimum_usable_duration_ratio", 0.55))
    long_ratio = float(policy.get("long_capture_warning_ratio", 2.50))
    min_short_edge = int(policy.get("minimum_short_edge_px", 720))
    preferred_fps = float(policy.get("preferred_frame_rate_fps", 30) or 30)
    preferred_audio_rate = int(policy.get("preferred_audio_sample_rate_hz", 48000) or 48000)

    files: list[dict[str, Any]] = []
    unmatched: list[str] = []
    blockers: list[str] = []
    duplicate_keys: set[tuple[str, int, str, str]] = set()
    seen_keys: set[tuple[str, int, str, str]] = set()

    for path in sorted(p for p in input_dir.rglob("*") if p.is_file()):
        parsed = parse_capture_filename(path)
        if parsed is None:
            continue
        relative = path.relative_to(input_dir).as_posix()
        if not parsed.get("matched"):
            unmatched.append(relative)
            continue
        take_id = str(parsed["take_id"])
        key = (
            take_id,
            int(parsed["retake_number"]),
            str(parsed["media_type"]),
            str(parsed["label"]),
        )
        if key in seen_keys:
            duplicate_keys.add(key)
            continue
        seen_keys.add(key)
        if take_id not in expected:
            blockers.append(f"unknown_take_id:{take_id}")
        inspection = (
            inspect_media(path)
            if parsed["media_type"] == "video"
            else inspect_audio(path)
        )
        files.append(
            {
                **parsed,
                "relative_path": relative,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "inspection": inspection,
            }
        )

    for take_id, retake, media_type, label in sorted(duplicate_keys):
        blockers.append(
            f"duplicate_capture_identity:{take_id}:r{retake:02d}:{media_type}:{label}"
        )

    groups: dict[str, dict[int, dict[str, list[dict[str, Any]]]]] = {}
    for item in files:
        take_id = str(item["take_id"])
        if take_id not in expected:
            continue
        retake = int(item["retake_number"])
        bucket = groups.setdefault(take_id, {}).setdefault(
            retake, {"video": [], "audio": []}
        )
        bucket[str(item["media_type"])].append(item)

    take_results: list[dict[str, Any]] = []
    global_warnings: set[str] = set()
    for take_id, take in expected.items():
        expected_seconds = float(take.get("expected_capture_seconds", 0) or 0)
        candidates: list[dict[str, Any]] = []
        for retake, media in sorted(groups.get(take_id, {}).items()):
            video = _select_video(
                media["video"],
                expected_seconds=expected_seconds,
                preferred_labels=preferred_labels,
            )
            external_audio = _select_audio(
                media["audio"], expected_seconds=expected_seconds
            )
            issues: list[str] = []
            usable = True
            if video is None:
                usable = False
                issues.append("no_healthy_video")
                duration_ratio = 0.0
            else:
                inspection = video["inspection"]
                duration = float(inspection.get("duration_seconds", 0) or 0)
                duration_ratio = duration / expected_seconds if expected_seconds > 0 else 1.0
                if duration_ratio < min_duration_ratio:
                    usable = False
                    issues.append("capture_too_short")
                elif duration_ratio > long_ratio:
                    issues.append("capture_unusually_long")
                width = int(inspection.get("width", 0) or 0)
                height = int(inspection.get("height", 0) or 0)
                if width and height and min(width, height) < min_short_edge:
                    issues.append("low_resolution")
                rate = str(inspection.get("r_frame_rate", "") or "")
                if rate and "/" in rate:
                    left, right = rate.split("/", 1)
                    try:
                        actual_fps = float(left) / max(float(right), 1e-9)
                        if abs(actual_fps - preferred_fps) > 0.75:
                            issues.append("frame_rate_differs_from_recommendation")
                    except ValueError:
                        pass

            embedded_audio_ok = bool(
                video and video.get("inspection", {}).get("has_audio_stream")
            )
            usable_external_audio = external_audio
            if external_audio:
                external_duration = float(
                    external_audio["inspection"].get("duration_seconds", 0) or 0
                )
                external_ratio = (
                    external_duration / expected_seconds
                    if expected_seconds > 0
                    else 1.0
                )
                if external_ratio < min_duration_ratio:
                    issues.append("external_audio_too_short")
                    usable_external_audio = None
            audio_source = (
                "external"
                if usable_external_audio
                else ("embedded" if embedded_audio_ok else "none")
            )
            if audio_source == "none":
                usable = False
                issues.append("missing_audio_source")
            if usable_external_audio:
                sample_rate = int(
                    usable_external_audio["inspection"].get("sample_rate_hz", 0) or 0
                )
                if sample_rate and sample_rate != preferred_audio_rate:
                    issues.append("audio_sample_rate_differs_from_recommendation")

            score = 0.0
            if video and video.get("inspection", {}).get("ok"):
                insp = video["inspection"]
                pixels = int(insp.get("width", 0) or 0) * int(
                    insp.get("height", 0) or 0
                )
                score += (
                    _duration_score(
                        float(insp.get("duration_seconds", 0) or 0),
                        expected_seconds,
                    )
                    * 60.0
                )
                score += min(1.0, pixels / float(3840 * 2160)) * 25.0
                score += 5.0 if embedded_audio_ok else 0.0
            if usable_external_audio:
                score += 8.0
            if not usable:
                score = min(score, 49.0)

            for issue in issues:
                global_warnings.add(issue)
            candidates.append(
                {
                    "retake_number": retake,
                    "status": (
                        "usable_technical" if usable else "unusable_technical"
                    ),
                    "technical_score": round(score, 3),
                    "duration_ratio": round(duration_ratio, 4),
                    "selected_video": (
                        {
                            "relative_path": video["relative_path"],
                            "label": video["label"],
                            "inspection": video["inspection"],
                            "sha256": video["sha256"],
                        }
                        if video
                        else None
                    ),
                    "selected_external_audio": (
                        {
                            "relative_path": usable_external_audio["relative_path"],
                            "label": usable_external_audio["label"],
                            "inspection": usable_external_audio["inspection"],
                            "sha256": usable_external_audio["sha256"],
                        }
                        if usable_external_audio
                        else None
                    ),
                    "audio_source": audio_source,
                    "issues": sorted(set(issues)),
                    "all_video_files": [
                        item["relative_path"] for item in media["video"]
                    ],
                    "all_audio_files": [
                        item["relative_path"] for item in media["audio"]
                    ],
                }
            )

        usable_candidates = [
            item for item in candidates if item["status"] == "usable_technical"
        ]
        selected = (
            max(
                usable_candidates,
                key=lambda item: (
                    float(item["technical_score"]),
                    int(item["retake_number"]),
                ),
            )
            if usable_candidates
            else None
        )
        if not candidates:
            blockers.append(f"missing_take:{take_id}")
        elif not selected:
            blockers.append(f"no_usable_candidate:{take_id}")

        take_results.append(
            {
                "take_id": take_id,
                "expected_capture_seconds": expected_seconds,
                "retake_count": len(candidates),
                "technical_preferred_retake": (
                    int(selected["retake_number"]) if selected else None
                ),
                "technical_preferred": selected,
                "candidates": candidates,
            }
        )

    unique_blockers = sorted(set(blockers))
    complete = [item for item in take_results if item["technical_preferred"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "episode_date": contract["episode_date"],
        "status": "ready_for_alignment" if not unique_blockers else "ingest_incomplete",
        "source": {
            "recording_ingest_contract": (
                f"scripts/{contract['episode_date']}/recording_ingest_contract.json"
            ),
            "input_root_name": input_dir.name,
            "absolute_input_path_persisted": False,
        },
        "selection_policy": dict(contract.get("selection_policy", {})),
        "readiness": {
            "ready_for_alignment": not unique_blockers,
            "blockers": unique_blockers,
            "warnings": sorted(
                global_warnings
                | ({f"unmatched_files:{len(unmatched)}"} if unmatched else set())
            ),
        },
        "summary": {
            "expected_take_count": len(expected),
            "take_count_with_candidate": len(complete),
            "missing_or_unusable_take_count": len(expected) - len(complete),
            "discovered_media_file_count": len(files),
            "unmatched_media_file_count": len(unmatched),
            "take_count_with_multiple_retakes": sum(
                1 for item in take_results if int(item["retake_count"]) > 1
            ),
        },
        "unmatched_files": unmatched,
        "files": files,
        "takes": take_results,
    }


def write_ingest_manifest(
    *,
    episode_dir: Path,
    input_dir: Path,
    enforce: bool,
) -> tuple[Path, dict[str, Any]]:
    contract_path = episode_dir / "recording_ingest_contract.json"
    if not contract_path.is_file():
        raise FileNotFoundError(f"Missing ingest contract: {contract_path}")
    manifest = scan_recordings(
        contract=_read_json(contract_path),
        input_dir=input_dir,
    )
    validate_payload(manifest, "recording_ingest_manifest.schema.json")
    destination = episode_dir / "recording_ingest_manifest.json"
    destination.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if enforce and not manifest["readiness"]["ready_for_alignment"]:
        raise RuntimeError(
            "Recording ingest is not ready for alignment: "
            + ", ".join(manifest["readiness"]["blockers"])
        )
    return destination, manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare or scan the Recording Ingest Contract"
    )
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--scripts-dir", default="scripts")
    parser.add_argument("--input-dir", default="")
    parser.add_argument("--enforce", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.repo_root).resolve()
    episode_dir = root / args.scripts_dir / args.target_date
    contract_path, instructions_path, _ = write_ingest_contract(
        episode_dir=episode_dir
    )
    result: dict[str, Any] = {
        "recording_ingest_contract": str(contract_path),
        "recording_ingest_instructions": str(instructions_path),
        "scan_performed": False,
    }
    if args.input_dir:
        manifest_path, manifest = write_ingest_manifest(
            episode_dir=episode_dir,
            input_dir=Path(args.input_dir).resolve(),
            enforce=args.enforce,
        )
        result.update(
            {
                "scan_performed": True,
                "recording_ingest_manifest": str(manifest_path),
                "ready_for_alignment": manifest["readiness"][
                    "ready_for_alignment"
                ],
                "blockers": manifest["readiness"]["blockers"],
            }
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
