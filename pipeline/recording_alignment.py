from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml

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


def _read_policy(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("recording_alignment.yaml must contain an object")
    return payload


def _normalize_token(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w]+", "", text, flags=re.UNICODE)
    return text


def tokenize(value: str) -> list[str]:
    return [
        token
        for token in (_normalize_token(part) for part in str(value or "").split())
        if token
    ]


def build_alignment_contract(
    *,
    recording_pack: dict[str, Any],
    ingest_contract: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    episode_date = str(recording_pack.get("episode_date", "") or "").strip()
    if not episode_date or episode_date != str(ingest_contract.get("episode_date", "") or ""):
        raise ValueError("Recording Pack and ingest contract episode_date must match")
    takes = [dict(item) for item in recording_pack.get("takes", []) if isinstance(item, dict)]
    if not takes:
        raise ValueError("Recording Pack has no takes")

    expected = []
    for take in takes:
        take_id = str(take.get("take_id", "") or "").strip()
        text = str(take.get("spoken_text", "") or "").strip()
        tokens = tokenize(text)
        if not take_id or not tokens:
            raise ValueError("Every recording take requires take_id and spoken_text")
        expected.append(
            {
                "take_id": take_id,
                "section_label": str(take.get("section_label", "") or ""),
                "expected_text": text,
                "expected_word_count": len(tokens),
                "technical_preference_is_provisional": True,
            }
        )

    resolve_policy = policy.get("resolve", {}) if isinstance(policy.get("resolve"), dict) else {}
    transcription = (
        policy.get("transcription", {})
        if isinstance(policy.get("transcription"), dict)
        else {}
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "episode_date": episode_date,
        "status": "awaiting_recording_alignment",
        "sources": {
            "recording_pack": f"scripts/{episode_date}/recording_pack.json",
            "recording_ingest_contract": f"scripts/{episode_date}/recording_ingest_contract.json",
        },
        "policy": policy,
        "providers": {
            "primary_transcription": str(
                transcription.get("primary_provider", "whisperx_local")
            ),
            "resolve_native_transcription": {
                "role": str(
                    transcription.get("resolve_native_role", "diagnostic_optional")
                ),
                "reason": (
                    "Resolve may transcribe locally, but the neutral alignment contract "
                    "requires complete word timestamps and does not depend on Resolve transcript extraction."
                ),
            },
            "whisperx": {
                "required_as_repo_dependency": False,
                "execution_scope": "local_only_after_recording",
                "requires_word_timestamps": bool(
                    transcription.get("require_word_timestamps", True)
                ),
                "transcribe_all_usable_retakes": bool(
                    transcription.get("transcribe_all_usable_retakes", True)
                ),
            },
        },
        "resolve_handoff": {
            "primary_postproduction_host": str(
                resolve_policy.get("primary_postproduction_host", "davinci_resolve")
            ),
            "external_audio_sync": str(
                resolve_policy.get("external_audio_sync", "waveform")
            ),
            "retain_embedded_audio_during_sync": bool(
                resolve_policy.get("retain_embedded_audio_during_sync", True)
            ),
            "create_new_aligned_timeline": bool(
                resolve_policy.get("create_new_aligned_timeline", True)
            ),
            "never_overwrite_existing_timeline": bool(
                resolve_policy.get("never_overwrite_existing_timeline", True)
            ),
            "native_transcription_is_not_alignment_authority": bool(
                resolve_policy.get(
                    "native_transcription_is_not_alignment_authority", True
                )
            ),
        },
        "expected_takes": expected,
        "readiness": {
            "contract_valid": True,
            "ready_for_transcription": False,
            "ready_for_alignment": False,
            "blockers": ["recording_ingest_manifest_required"],
        },
    }


def _word_edit_alignment(
    expected: list[str],
    actual: list[str],
) -> dict[str, Any]:
    n = len(expected)
    m = len(actual)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    back: list[list[str | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i
        back[i][0] = "delete"
    for j in range(1, m + 1):
        dp[0][j] = j
        back[0][j] = "insert"

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            equal = expected[i - 1] == actual[j - 1]
            choices = [
                (dp[i - 1][j] + 1, "delete"),
                (dp[i][j - 1] + 1, "insert"),
                (dp[i - 1][j - 1] + (0 if equal else 1), "match" if equal else "substitute"),
            ]
            cost, op = min(
                choices,
                key=lambda item: (
                    item[0],
                    {"match": 0, "substitute": 1, "delete": 2, "insert": 3}[item[1]],
                ),
            )
            dp[i][j] = cost
            back[i][j] = op

    i, j = n, m
    operations: list[dict[str, Any]] = []
    while i > 0 or j > 0:
        op = back[i][j]
        if op in {"match", "substitute"}:
            operations.append(
                {
                    "op": op,
                    "expected_index": i - 1,
                    "actual_index": j - 1,
                }
            )
            i -= 1
            j -= 1
        elif op == "delete":
            operations.append(
                {"op": op, "expected_index": i - 1, "actual_index": None}
            )
            i -= 1
        elif op == "insert":
            operations.append(
                {"op": op, "expected_index": None, "actual_index": j - 1}
            )
            j -= 1
        else:
            raise RuntimeError("Alignment backtrace became inconsistent")
    operations.reverse()

    counts = {
        "matches": sum(1 for x in operations if x["op"] == "match"),
        "substitutions": sum(1 for x in operations if x["op"] == "substitute"),
        "deletions": sum(1 for x in operations if x["op"] == "delete"),
        "insertions": sum(1 for x in operations if x["op"] == "insert"),
    }
    wer = (
        counts["substitutions"] + counts["deletions"] + counts["insertions"]
    ) / max(1, n)
    expected_coverage = (n - counts["deletions"]) / max(1, n)
    mapped_actual = [
        int(item["actual_index"])
        for item in operations
        if item["actual_index"] is not None
        and item["expected_index"] is not None
        and item["op"] in {"match", "substitute"}
    ]
    return {
        **counts,
        "word_error_rate": round(wer, 4),
        "expected_word_coverage": round(expected_coverage, 4),
        "mapped_actual_indices": mapped_actual,
    }


def _flatten_words(item: dict[str, Any]) -> list[dict[str, Any]]:
    words = [dict(x) for x in item.get("words", []) if isinstance(x, dict)]
    cleaned = []
    previous_end = 0.0
    for word in words:
        token = str(word.get("word", "") or "").strip()
        if not token:
            continue
        start = float(word.get("start", 0) or 0)
        end = float(word.get("end", start) or start)
        if end < start:
            raise ValueError("Transcript word end precedes start")
        if start + 0.05 < previous_end:
            raise ValueError("Transcript word timestamps are not monotonic")
        previous_end = max(previous_end, end)
        cleaned.append(
            {
                "word": token,
                "normalized": _normalize_token(token),
                "start": round(start, 3),
                "end": round(end, 3),
                "score": (
                    float(word["score"])
                    if word.get("score") is not None
                    else None
                ),
            }
        )
    return [item for item in cleaned if item["normalized"]]


def _candidate_alignment(
    *,
    take: dict[str, Any],
    candidate: dict[str, Any],
    transcript: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    expected_tokens = tokenize(str(take.get("spoken_text", "") or ""))
    words = _flatten_words(transcript)
    actual_tokens = [str(item["normalized"]) for item in words]
    edits = _word_edit_alignment(expected_tokens, actual_tokens)

    scores = [
        float(item["score"])
        for item in words
        if item.get("score") is not None
    ]
    mean_confidence = sum(scores) / len(scores) if scores else None

    mapped = edits.pop("mapped_actual_indices")
    trim_policy = policy.get("trimming", {})
    if mapped:
        first = words[min(mapped)]
        last = words[max(mapped)]
        trim_in = max(
            0.0,
            float(first["start"])
            - float(trim_policy.get("pre_word_handle_seconds", 0.30)),
        )
        trim_out = (
            float(last["end"])
            + float(trim_policy.get("post_word_handle_seconds", 0.45))
        )
    else:
        trim_in = 0.0
        trim_out = 0.0

    video = (
        candidate.get("selected_video", {})
        if isinstance(candidate.get("selected_video"), dict)
        else {}
    )
    video_inspection = (
        video.get("inspection", {})
        if isinstance(video.get("inspection"), dict)
        else {}
    )
    source_duration = float(video_inspection.get("duration_seconds", 0) or 0)
    if source_duration > 0:
        trim_out = min(trim_out, source_duration)
    trim_duration = max(0.0, trim_out - trim_in)

    selection = policy.get("selection", {})
    weights = selection.get("weights", {})
    transcript_accuracy = max(0.0, 1.0 - float(edits["word_error_rate"]))
    expected_coverage = float(edits["expected_word_coverage"])
    confidence_component = (
        float(mean_confidence) if mean_confidence is not None else 0.75
    )
    technical_score = min(
        1.0,
        max(0.0, float(candidate.get("technical_score", 0) or 0) / 100.0),
    )
    composite = (
        transcript_accuracy * float(weights.get("transcript_accuracy", 0.65))
        + expected_coverage * float(weights.get("expected_word_coverage", 0.20))
        + confidence_component * float(weights.get("mean_word_confidence", 0.10))
        + technical_score * float(weights.get("technical_ingest_score", 0.05))
    )

    issues: list[str] = []
    if edits["word_error_rate"] > float(
        selection.get("max_word_error_rate_for_auto_select", 0.12)
    ):
        issues.append("word_error_rate_above_auto_select")
    if expected_coverage < float(
        selection.get("min_expected_word_coverage_for_auto_select", 0.94)
    ):
        issues.append("expected_word_coverage_below_auto_select")
    if mean_confidence is not None and mean_confidence < float(
        selection.get("min_mean_word_confidence_when_available", 0.55)
    ):
        issues.append("mean_word_confidence_below_auto_select")
    if trim_duration < float(
        trim_policy.get("min_clip_duration_seconds", 0.50)
    ):
        issues.append("aligned_trim_too_short")
    if str(transcript.get("timebase", "") or "video_source") != "video_source":
        issues.append("video_timebase_requires_resolve_waveform_sync")

    return {
        "retake_number": int(candidate.get("retake_number", 0) or 0),
        "technical_score": float(candidate.get("technical_score", 0) or 0),
        "transcript_provider": str(transcript.get("provider", "") or ""),
        "source_relative_path": str(
            transcript.get("source_relative_path", "") or ""
        ),
        "timebase": str(transcript.get("timebase", "") or "video_source"),
        "transcript_text": str(transcript.get("text", "") or ""),
        "word_count": len(words),
        "mean_word_confidence": (
            round(mean_confidence, 4) if mean_confidence is not None else None
        ),
        "metrics": edits,
        "trim": {
            "source_in_seconds": round(trim_in, 3),
            "source_out_seconds": round(trim_out, 3),
            "duration_seconds": round(trim_duration, 3),
        },
        "audio_source": str(candidate.get("audio_source", "") or ""),
        "video": video,
        "external_audio": candidate.get("selected_external_audio"),
        "selection_score": round(composite, 4),
        "auto_select_eligible": not [
            issue
            for issue in issues
            if issue != "video_timebase_requires_resolve_waveform_sync"
        ],
        "video_trim_ready": (
            str(transcript.get("timebase", "") or "video_source") == "video_source"
        ),
        "issues": issues,
    }


def build_recording_alignment(
    *,
    recording_pack: dict[str, Any],
    ingest_manifest: dict[str, Any],
    transcript_bundle: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    episode_date = str(recording_pack.get("episode_date", "") or "")
    if not episode_date:
        raise ValueError("Recording Pack episode_date is required")
    for payload, label in (
        (ingest_manifest, "recording_ingest_manifest"),
        (transcript_bundle, "recording_transcript_bundle"),
    ):
        if str(payload.get("episode_date", "") or "") != episode_date:
            raise ValueError(f"{label} episode_date does not match Recording Pack")

    transcripts = {}
    for item in transcript_bundle.get("items", []):
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("take_id", "") or ""),
            int(item.get("retake_number", 0) or 0),
        )
        if not key[0] or key[1] <= 0:
            continue
        if key in transcripts:
            raise ValueError(
                f"Duplicate transcript for {key[0]} r{key[1]:02d}"
            )
        normalized = dict(item)
        normalized["provider"] = str(transcript_bundle.get("provider", "") or "")
        transcripts[key] = normalized

    ingest_by_take = {
        str(item.get("take_id", "") or ""): item
        for item in ingest_manifest.get("takes", [])
        if isinstance(item, dict)
    }

    selection_policy = policy.get("selection", {})
    ambiguity_margin = float(
        selection_policy.get("ambiguity_score_margin", 0.03)
    )
    take_results: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: set[str] = set()
    aligned_seconds = 0.0

    for take in recording_pack.get("takes", []):
        if not isinstance(take, dict):
            continue
        take_id = str(take.get("take_id", "") or "")
        ingest_take = ingest_by_take.get(take_id)
        if not ingest_take:
            blockers.append(f"missing_ingest_take:{take_id}")
            take_results.append(
                {
                    "take_id": take_id,
                    "recommended_retake": None,
                    "final_selected_retake": None,
                    "needs_human_review": True,
                    "reason": "missing_ingest_take",
                    "candidates": [],
                }
            )
            continue

        candidates = []
        for candidate in ingest_take.get("candidates", []):
            if not isinstance(candidate, dict):
                continue
            if candidate.get("status") != "usable_technical":
                continue
            retake = int(candidate.get("retake_number", 0) or 0)
            transcript = transcripts.get((take_id, retake))
            if not transcript:
                warnings.add(f"missing_transcript:{take_id}:r{retake:02d}")
                continue
            candidates.append(
                _candidate_alignment(
                    take=take,
                    candidate=candidate,
                    transcript=transcript,
                    policy=policy,
                )
            )

        candidates.sort(
            key=lambda item: (
                float(item["selection_score"]),
                -float(item["metrics"]["word_error_rate"]),
                int(item["retake_number"]),
            ),
            reverse=True,
        )
        recommended = candidates[0] if candidates else None
        eligible = [item for item in candidates if item["auto_select_eligible"]]
        final = eligible[0] if eligible else None
        ambiguous = False
        if final and len(eligible) > 1:
            ambiguous = (
                float(eligible[0]["selection_score"])
                - float(eligible[1]["selection_score"])
                < ambiguity_margin
            )
            if ambiguous:
                final = None
                warnings.add(f"ambiguous_retake_selection:{take_id}")

        needs_review = final is None
        if recommended is None:
            blockers.append(f"missing_transcript_take:{take_id}")
        elif final is None:
            blockers.append(f"retake_requires_human_review:{take_id}")
        else:
            aligned_seconds += float(final["trim"]["duration_seconds"])
            if not bool(final.get("video_trim_ready")):
                blockers.append(
                    f"resolve_waveform_sync_offset_required:{take_id}"
                )

        take_results.append(
            {
                "take_id": take_id,
                "recommended_retake": (
                    int(recommended["retake_number"]) if recommended else None
                ),
                "final_selected_retake": (
                    int(final["retake_number"]) if final else None
                ),
                "needs_human_review": needs_review,
                "ambiguous": ambiguous,
                "selected": final,
                "candidates": candidates,
            }
        )

    unique_blockers = sorted(set(blockers))
    review_count = sum(1 for item in take_results if item["needs_human_review"])
    missing_count = sum(
        1 for item in take_results if item.get("reason") == "missing_ingest_take"
        or not item.get("candidates")
    )
    status = (
        "aligned"
        if not unique_blockers
        else (
            "needs_human_review"
            if any(x.startswith("retake_requires_human_review:") for x in unique_blockers)
            else "alignment_incomplete"
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "episode_date": episode_date,
        "status": status,
        "sources": {
            "recording_pack": f"scripts/{episode_date}/recording_pack.json",
            "recording_ingest_manifest": f"scripts/{episode_date}/recording_ingest_manifest.json",
            "transcript_provider": str(
                transcript_bundle.get("provider", "") or ""
            ),
        },
        "policy": policy,
        "summary": {
            "take_count": len(take_results),
            "auto_selected_take_count": sum(
                1 for item in take_results if item["final_selected_retake"] is not None
            ),
            "review_take_count": review_count,
            "missing_transcript_take_count": missing_count,
            "aligned_spoken_seconds": round(aligned_seconds, 3),
        },
        "readiness": {
            "ready_for_aligned_timeline": not unique_blockers,
            "ready_for_resolve_handoff": not any(
                blocker.startswith(("missing_ingest_take:", "missing_transcript_take:", "retake_requires_human_review:"))
                for blocker in unique_blockers
            ),
            "requires_resolve_waveform_sync_count": sum(
                1
                for blocker in unique_blockers
                if blocker.startswith("resolve_waveform_sync_offset_required:")
            ),
            "blockers": unique_blockers,
            "warnings": sorted(warnings),
        },
        "takes": take_results,
    }


def write_alignment_contract(
    *,
    episode_dir: Path,
    policy_path: Path,
) -> tuple[Path, dict[str, Any]]:
    recording_pack = _read_json(episode_dir / "recording_pack.json")
    ingest_contract = _read_json(
        episode_dir / "recording_ingest_contract.json"
    )
    policy = _read_policy(policy_path)
    payload = build_alignment_contract(
        recording_pack=recording_pack,
        ingest_contract=ingest_contract,
        policy=policy,
    )
    validate_payload(payload, "recording_alignment_contract.schema.json")
    destination = episode_dir / "recording_alignment_contract.json"
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination, payload


def write_recording_alignment(
    *,
    episode_dir: Path,
    transcript_bundle_path: Path,
    policy_path: Path,
    enforce: bool,
) -> tuple[Path, dict[str, Any]]:
    recording_pack = _read_json(episode_dir / "recording_pack.json")
    ingest_manifest = _read_json(
        episode_dir / "recording_ingest_manifest.json"
    )
    transcript_bundle = _read_json(transcript_bundle_path)
    validate_payload(
        transcript_bundle,
        "recording_transcript_bundle.schema.json",
    )
    policy = _read_policy(policy_path)
    result = build_recording_alignment(
        recording_pack=recording_pack,
        ingest_manifest=ingest_manifest,
        transcript_bundle=transcript_bundle,
        policy=policy,
    )
    validate_payload(result, "recording_alignment.schema.json")
    destination = episode_dir / "recording_alignment.json"
    destination.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if enforce and not result["readiness"]["ready_for_aligned_timeline"]:
        raise RuntimeError(
            "Recording alignment requires review: "
            + ", ".join(result["readiness"]["blockers"])
        )
    return destination, result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the recording alignment contract or align transcribed retakes"
    )
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--scripts-dir", default="scripts")
    parser.add_argument(
        "--policy", default="config/recording_alignment.yaml"
    )
    parser.add_argument("--transcript-bundle", default="")
    parser.add_argument("--enforce", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.repo_root).resolve()
    episode_dir = root / args.scripts_dir / args.target_date
    policy_path = root / args.policy
    contract_path, _ = write_alignment_contract(
        episode_dir=episode_dir,
        policy_path=policy_path,
    )
    output: dict[str, Any] = {
        "recording_alignment_contract": str(contract_path),
        "alignment_performed": False,
    }
    if args.transcript_bundle:
        alignment_path, result = write_recording_alignment(
            episode_dir=episode_dir,
            transcript_bundle_path=Path(args.transcript_bundle).resolve(),
            policy_path=policy_path,
            enforce=args.enforce,
        )
        output.update(
            {
                "alignment_performed": True,
                "recording_alignment": str(alignment_path),
                "ready_for_aligned_timeline": result["readiness"][
                    "ready_for_aligned_timeline"
                ],
                "blockers": result["readiness"]["blockers"],
            }
        )
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
