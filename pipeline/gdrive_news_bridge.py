from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from pipeline.staged_news_issue import process_event

ENVELOPE_KEYS = {
    "format",
    "schema_version",
    "message_id",
    "target_repo",
    "target_path",
    "content_type",
    "sha256",
    "payload_b64",
}
MESSAGE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{6,160}$")
TARGET_RE = re.compile(
    r"^news/(?P<date>\\d{4}-\\d{2}-\\d{2})-(?P<hour>\\d{2})-(?P<minute>\\d{2})-(?P<second>\\d{2})\\.txt$"
)


def _write_output(name: str, value: str) -> None:
    output = os.getenv("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\\n")


def parse_envelope(path: Path) -> dict[str, str]:
    raw = path.read_text(encoding="utf-8-sig")
    env: dict[str, str] = {}
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "=" not in line:
            raise ValueError(f"línea de envelope inválida: {line!r}")
        key, value = line.split("=", 1)
        if key in env:
            raise ValueError(f"clave duplicada en envelope: {key}")
        env[key] = value

    if set(env) != ENVELOPE_KEYS:
        raise ValueError(
            f"claves de envelope inválidas: got={sorted(env)} expected={sorted(ENVELOPE_KEYS)}"
        )
    if env["format"] != "base64-payload-v1":
        raise ValueError("format no soportado")
    if env["schema_version"] != "1.0":
        raise ValueError("schema_version no soportado")
    if not MESSAGE_ID_RE.fullmatch(env["message_id"]):
        raise ValueError("message_id inválido")
    if not env["message_id"].startswith("ai-news-daily.news."):
        raise ValueError("message_id fuera del namespace de producción de AI News")
    if env["content_type"] != "text/plain":
        raise ValueError("content_type debe ser text/plain")
    return env


def decode_payload(env: dict[str, str]) -> str:
    try:
        payload = base64.b64decode(env["payload_b64"], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("payload_b64 inválido") from exc

    actual_sha = hashlib.sha256(payload).hexdigest()
    if actual_sha != env["sha256"]:
        raise ValueError(f"sha256 mismatch: {actual_sha} != {env['sha256']}")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("payload no es UTF-8 válido") from exc


def process_envelope(
    envelope_path: Path,
    expected_repo: str,
    news_dir: Path,
) -> tuple[str, Path | None, str, str]:
    env = parse_envelope(envelope_path)
    if env["target_repo"] != expected_repo:
        raise ValueError(f"target_repo mismatch: {env['target_repo']} != {expected_repo}")

    target_match = TARGET_RE.fullmatch(env["target_path"])
    if not target_match:
        raise ValueError("target_path debe ser news/YYYY-MM-DD-HH-MM-SS.txt")

    stamp = (
        f"{target_match.group('date')} "
        f"{target_match.group('hour')}:{target_match.group('minute')}:{target_match.group('second')}"
    )
    payload = decode_payload(env).strip()
    expected_header = f"# AI News Daily — {stamp} America/Mexico_City"
    if not payload or payload.splitlines()[0].strip() != expected_header:
        raise ValueError("target_path y encabezado del digest no coinciden")

    with tempfile.TemporaryDirectory() as tmp:
        event_path = Path(tmp) / "event.json"
        event_path.write_text(
            json.dumps(
                {
                    "issue": {
                        "title": f"AI_NEWS_STAGING — {stamp} America/Mexico_City",
                        "body": payload,
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        status, output = process_event(event_path, news_dir)

    if status == "created":
        expected_output = news_dir / env["target_path"].removeprefix("news/")
        if output != expected_output:
            raise ValueError(f"ruta materializada inesperada: {output} != {expected_output}")

    digest_date = target_match.group("date")
    _write_output("status", status)
    _write_output("path", str(output or ""))
    _write_output("date", digest_date)
    _write_output("message_id", env["message_id"])
    return status, output, digest_date, env["message_id"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--envelope", type=Path, required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--news-dir", type=Path, default=Path("news"))
    args = parser.parse_args(argv)

    try:
        status, output, digest_date, message_id = process_envelope(
            args.envelope, args.repo, args.news_dir
        )
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"{status}: {output} date={digest_date} message_id={message_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
