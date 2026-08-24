from __future__ import annotations

import json
import shutil
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _split_script(script: str) -> tuple[str, str, str]:
    words = script.split()
    if len(words) < 9:
        # Visual planning only needs non-empty duration-bearing sections.
        words = words + ["…"] * (9 - len(words))
    opening_end = max(1, round(len(words) * 0.12))
    synthesis_start = max(opening_end + 1, round(len(words) * 0.88))
    synthesis_start = min(synthesis_start, len(words) - 1)
    opening = " ".join(words[:opening_end]).strip()
    body = " ".join(words[opening_end:synthesis_start]).strip()
    synthesis = " ".join(words[synthesis_start:]).strip()
    return opening, body or "Desarrollo visual del ensayo.", synthesis


def prepare_legacy_media_episode(source_dir: Path, destination_dir: Path) -> bool:
    """Create a temporary, explicitly synthetic media-only structure for legacy episodes.

    Returns True when compatibility metadata was injected. The source episode is never
    modified. These files exist only so current dense visual planners can distribute media
    across an old script; they are not evidence, editorial structure, or canonical history.
    """
    if destination_dir.exists():
        shutil.rmtree(destination_dir)
    shutil.copytree(source_dir, destination_dir)

    plan_path = destination_dir / "episode_plan.json"
    sections_path = destination_dir / "script_sections.json"
    if plan_path.exists() and sections_path.exists():
        return False

    script_path = destination_dir / "script.txt"
    if not script_path.exists():
        raise FileNotFoundError(f"Missing script: {source_dir / 'script.txt'}")
    script = script_path.read_text(encoding="utf-8").strip()
    opening, body, synthesis = _split_script(script)

    _write_json(
        plan_path,
        {
            "schema_version": 0,
            "media_compatibility_only": True,
            "legacy_contract": True,
            "hook": "Legacy episode visual planning",
            "central_question": "Legacy episode visual planning",
            "thesis": "Legacy episode visual planning",
            "evidence": [],
            "claim_ledger": [],
            "beats": [
                {
                    "beat_id": "legacy_body",
                    "kind": "reflection",
                    "purpose": "Distribute visual changes across the historical script without inventing evidence.",
                    "evidence_ids": [],
                }
            ],
        },
    )
    _write_json(
        sections_path,
        {
            "schema_version": 0,
            "media_compatibility_only": True,
            "sections": [
                {
                    "section_key": "opening",
                    "kind": "opening",
                    "beat_id": None,
                    "beat_kind": None,
                    "evidence_ids": [],
                    "spoken_text": opening,
                    "word_count": len(opening.split()),
                },
                {
                    "section_key": "beat:legacy_body",
                    "kind": "development",
                    "beat_id": "legacy_body",
                    "beat_kind": "reflection",
                    "evidence_ids": [],
                    "spoken_text": body,
                    "word_count": len(body.split()),
                },
                {
                    "section_key": "synthesis",
                    "kind": "synthesis",
                    "beat_id": None,
                    "beat_kind": None,
                    "evidence_ids": [],
                    "spoken_text": synthesis,
                    "word_count": len(synthesis.split()),
                },
            ],
        },
    )
    return True
