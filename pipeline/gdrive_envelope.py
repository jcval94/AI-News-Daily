from __future__ import annotations

import base64
import binascii
import hashlib
import re
from pathlib import Path

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


def parse_envelope(
    path: Path,
    *,
    message_prefix: str,
    expected_repo: str,
    expected_content_type: str,
) -> dict[str, str]:
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
    if not env["message_id"].startswith(message_prefix):
        raise ValueError(f"message_id fuera del namespace esperado: {message_prefix}")
    if env["target_repo"] != expected_repo:
        raise ValueError(f"target_repo mismatch: {env['target_repo']} != {expected_repo}")
    if env["content_type"] != expected_content_type:
        raise ValueError(
            f"content_type mismatch: {env['content_type']} != {expected_content_type}"
        )
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
