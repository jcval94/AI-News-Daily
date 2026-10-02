from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from pipeline.gdrive_envelope import decode_payload, parse_envelope
from pipeline.staged_narrative_memory_issue import HEADER_RE, process_event

MESSAGE_PREFIX = "ai-news-daily.narrative-memory."
TARGET_PATH = "editorial/narrative_memory.jsonl"


def _write_output(name: str, value: str) -> None:
    output = os.getenv("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def process_envelope(
    envelope_path: Path,
    expected_repo: str,
    memory_path: Path,
    *,
    apply: bool = False,
) -> tuple[str, list[str]]:
    env = parse_envelope(
        envelope_path,
        message_prefix=MESSAGE_PREFIX,
        expected_repo=expected_repo,
        expected_content_type="text/plain",
    )
    if env["target_path"] != TARGET_PATH:
        raise ValueError(f"target_path debe ser {TARGET_PATH}")

    payload = decode_payload(env).strip()
    if not payload:
        raise ValueError("payload vacío")

    first_line = payload.splitlines()[0].strip()
    match = HEADER_RE.fullmatch(first_line)
    if not match:
        raise ValueError("encabezado Narrative Memory inválido")

    stamp = f"{match.group('date')} {match.group('time')}"
    expected_message_id = (
        f"{MESSAGE_PREFIX}{match.group('date')}."
        f"{match.group('time').replace(':', '')}"
    )
    if env["message_id"] != expected_message_id:
        raise ValueError(
            f"message_id no coincide con timestamp del payload: "
            f"{env['message_id']} != {expected_message_id}"
        )

    with tempfile.TemporaryDirectory() as tmp:
        event_path = Path(tmp) / "event.json"
        event_path.write_text(
            json.dumps(
                {
                    "issue": {
                        "title": (
                            f"NARRATIVE_MEMORY_STAGING — {stamp} "
                            "America/Mexico_City"
                        ),
                        "body": payload,
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        status, ids = process_event(event_path, memory_path, apply=apply)

    _write_output("status", status)
    _write_output("ids", ",".join(ids))
    _write_output("added_count", "0" if status == "already_exists" else str(len(ids)))
    return status, ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--envelope", type=Path, required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument(
        "--memory",
        type=Path,
        default=Path(TARGET_PATH),
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    try:
        status, ids = process_envelope(
            args.envelope,
            args.repo,
            args.memory,
            apply=args.apply,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"{status}: {','.join(ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
